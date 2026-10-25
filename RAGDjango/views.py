import json
from typing import Any

from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from langchain.agents import create_agent
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from .llm import ChatModel
from .service import auth
from .tools.rag import is_index_ready, rag_stream
from .tools.tools import send_email, sql_query

# 记忆：同一个 thread_id 复用同一段对话上下文
memory = InMemorySaver()


# 邮件发送助手（大模型 + 工具调用）
def send_email_assistant(request: Any):  # request: 表示前端发送到后端的数据（请求方式、数据、类型）
    question = request.GET.get("question", "")
    session_id = request.GET.get("sessionId", "")

    if not question:
        return JsonResponse({"error": "缺少 question 参数"}, status=400)
    if not session_id:
        return JsonResponse({"error": "缺少 sessionId 参数"}, status=400)

    llm = ChatModel.load_model_once()

    # 提示词工程（第一个作用：设置大模型角色信息，第二个作用：约束大模型，告诉大模型它需要做什么/怎么做）
    prompt = """
        你是人工智能助手YOYO，是人工智能中的刘亦菲、是一个知心大姐姐，优雅、活波可爱，爱说土味情话，还是一个非常专业邮件攥写助手；
        请严格按照如下的工作流程进行工作，工作流程如下：
            第一步：判断用户输入的信息是标准的邮箱地址 还是 
            用户姓名
            第二步：如果是用户标准 邮箱地址，请按照如下流程工作：
                 1)理解用户真实意图和想法，理解用户邮件需求后，帮住用户提取邮箱主题、撰写邮件内容正文；
                 2)在撰写邮件内容的过程中，不调用邮件发送工具，撰写完成后将拟好的邮件内容以【邮件预览】的格式展示给用户；
                 3）当用户明确回答【确认发送】、【发送】、【可以发送了】等指令的时候，才调用工具[send_email]进行发送；
                 4）如果用户提供的信息不完整（比如缺少收件人邮箱、收件人姓名和称呼等关键信息）时，主动追问用户，不要猜测；
            第三步：如果用户输入的标识符信息，是用户姓名，那么请按照如下流程进行工作：
                 1) 从标识符中提取用户输入的 用户姓名
                 2）获取到用户姓名之后，调用 [sql_query] 这个工具根据username这个字段查询用户邮箱（email字段），分析查询结果，并获取到用户的邮箱地址
                 3）如果数据库返回数据为空列表，返回【数据库用户数据为空】，如果查询到用户数据但是邮箱为空，就返回【用户邮箱未注册】
                 4）获取到对应的邮箱地址后，执行第二步中的工作流程
    """

    # 1. 创建智能体
    agent = create_agent(
        model=llm,
        system_prompt=prompt,
        tools=[send_email, sql_query],  # tools 参数：大模型需要调用工具，使用 @tool 定义的方法
        checkpointer=memory,
        debug=True,
    )

    # 2. 调用智能体
    result = agent.invoke(
        input={"messages": [{"role": "user", "content": question}]},
        config={"configurable": {"thread_id": session_id}},  # sessionId 用户标识：隔离用户对话
    )

    print(result["messages"][-1].content)
    return JsonResponse({"result": result["messages"][-1].content})


"""
项目代码
"""


# 访问前端登录页面
def login_html(request: Any):
    return render(request=request, template_name="login.html")


# 跳转到主页的视图函数
# </index/>
def index_html(request: Any):
    return render(request, template_name="index.html")


# 发送验证码的视图
# </send_code/>
@csrf_exempt
def send_code(request: Any):
    data = json.loads(request.body)  # 前端传过来的是JSON字符串，需要反序列化成字典
    email = data.get("email")
    return auth.send_code(email)


# 验证码登录的视图
# </login_code/>
@csrf_exempt
def login_code(request: Any):
    data = json.loads(request.body)
    email = data.get("email")  # data["email"]
    code = data.get("code")
    return auth.login_code(email, code)


# data = YOLO, 请问
# data: 有什么可以帮你!
def sse_generator(generator_func):
    """将普通数据，封装为SSE数据流"""
    try:
        for chunk in generator_func:
            if chunk:  # 当chunk存在时，构建SSE数据流  data:{"data": "我是"}\n\n
                payload = json.dumps({"text": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
    except Exception as e:
        payload = json.dumps({"error": str(e)}, ensure_ascii=False)
        yield f"data: {payload}\n\n"
    finally:
        yield "data: [DONE]\n\n"


# </api/email/>
@csrf_exempt
@require_POST  # 前端发送fetch请求时，需要导入装饰器： from django.views.decorators.http import require_POST
def send_email_assis(request: Any):
    data = json.loads(request.body)
    question = data.get("question")
    sessionId = data.get("sessionId")
    llm = ChatModel.load_model_once()
    prompt = """
            你是人工智能助手YOYO，是人工智能中的刘亦菲、是一个知心大姐姐，优雅、活波可爱，爱说土味情话，还是一个非常专业邮件攥写助手；
            请严格按照如下的工作流程进行工作，工作流程如下：
                第一步：判断用户输入的信息是标准的邮箱地址 还是 用户姓名
                第二步：如果是用户标准 邮箱地址，请按照如下流程工作：
                     1)理解用户真实意图和想法，理解用户邮件需求后，帮住用户提取邮箱主题、撰写邮件内容正文HTML样式邮件；
                     2)在撰写邮件内容的过程中，不调用邮件发送工具，撰写完成后将拟好的邮件内容以【邮件预览】的格式展示给用户；
                     3）当用户明确回答【确认发送】、【发送】、【可以发送了】等指令的时候，才调用工具[send_email]进行发送；
                     4）如果用户提供的信息不完整（比如缺少收件人邮箱、收件人姓名和称呼等关键信息）时，主动追问用户，不要猜测；
                第三步：如果用户输入的标识符信息，是用户姓名，那么请按照如下流程进行工作：
                     1) 从标识符中提取用户输入的 用户姓名
                     2）获取到用户姓名之后，调用 [sql_query] 这个工具根据username这个字段查询用户邮箱（email字段），分析查询结果，并获取到用户的邮箱地址
                     3）如果数据库返回数据为空列表，返回【数据库用户数据为空】，如果查询到用户数据但是邮箱为空，就返回【用户邮箱为空】
                     4）获取到对应的邮箱地址后，执行第二步中的工作流程
            如果上面三个步骤不满足，那么执行第四步：
            第四步：如果用户需求不是发送邮件，而是简单的聊天，那么就不用调用任何工具，使用YOYO身份，与用户进行聊天   
               """  #可自定义修改

    # 3. 创建大模型智能体
    agent = create_agent(
        model=llm,  # model参数：表示使用的是哪个大模型
        system_prompt=prompt,  # system_prompt参数：提示词
        tools=[send_email, sql_query],  # tools参数：大模型需要调用工具，使用@tool定义的方法
        checkpointer=memory,
        debug=True,
    )

    # 调用生成器，将SSE数据流发送给前端
    def generate():
        for chunk, metadata in agent.stream(
            input={"messages": [{"role": "user", "content": question}]},
            config={"configurable": {"thread_id": sessionId}},  # sessionId用户标识：隔离用户对话
            stream_mode="messages",
        ):
            print("=========================")
            print(chunk, metadata)
            if chunk.content and not getattr(chunk, "tool_calls", None):
                yield chunk.content

    # from django.http import StreamingHttpResponse
    return StreamingHttpResponse(sse_generator(generate()), content_type="text/event-stream")


rag_store = {}  # 新建字典遍历，用来存储对话内容，存储RAG对话内容
chat_store = {}  # 存储chat聊天内容


# 基础聊天功能
# </api/chat/>
@csrf_exempt
@require_POST
def api_chat(request: Any):
    data = json.loads(request.body)
    question = data.get("question")
    sessionId = data.get("sessionId")
    llm = ChatModel.load_model_once()
    # 判断是否已经存在历史信息
    if sessionId not in chat_store:
        # from langchain_core.chat_history import InMemoryChatMessageHistory
        chat_store[sessionId] = InMemoryChatMessageHistory()
    history = chat_store[sessionId]

    def generate():
        full_response = ""
        # 将历史信息和当前用户信息，一起发送给大模型
        messages = history.messages + [HumanMessage(content=question)]
        # 流式输出
        for chunk in llm.stream(messages):
            if chunk.content:
                full_response += chunk.content
                yield chunk.content
        # 将消息存入chat_store中
        history.add_user_message(question)
        history.add_ai_message(full_response)

    return StreamingHttpResponse(sse_generator(generate()), content_type="text/event-stream")


# RAG 向量增强检索
# </api/rag/>
@csrf_exempt
@require_POST
def api_rag(request: Any):
    data = json.loads(request.body)
    question = data.get("question")

    if not question:
        return JsonResponse({"error": "缺少 question 参数"}, status=400)
    if not is_index_ready():
        return JsonResponse({"error": "向量库未构建，请先运行 tools/ingest.py"}, status=500)

    def generate():
        # rag_stream 内部：问题向量化 → 检索 Top-K 条文 → 拼 prompt → 大模型流式生成
        for chunk in rag_stream(question):
            yield chunk

    return StreamingHttpResponse(sse_generator(generate()), content_type="text/event-stream")
