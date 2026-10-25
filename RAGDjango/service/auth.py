from django.http import JsonResponse  # 将数据以JSON格式发送给前端
from langchain.agents import create_agent  # 创建智能体的库
from langgraph.checkpoint.memory import InMemorySaver  # 让大模型拥有记忆功能（内存记忆）
from ..llm import ChatModel
from ..tools.tools import send_email, sql_query
from .. import env
from pydantic import BaseModel, Field

import redis

# Redis 连接参数从环境变量读取，默认值用于本地开发（见 .env.example）
redis_conn = redis.Redis(
    host=env.get("REDIS_HOST", "127.0.0.1"),
    port=env.get_int("REDIS_PORT", 6379),
    db=env.get_int("REDIS_DB", 0),
    password=env.get("REDIS_PASSWORD") or None,
)  # redis默认16个数据库

# 初始化记忆功能
memory = InMemorySaver()


# 定义一个类接收大模型返回值
class EmailResp(BaseModel):
    code: str = Field(..., description="状态码")
    data: str = Field(..., description="验证码")
    msg: str = Field(..., description="提示信息")


# 写一个方法，用来供前端URL地址访问
def send_code(email):  # email: 前端传过来的邮箱地址
    # 1. 初始化大模型
    llm = ChatModel.load_model_once()

    # 2. 提示词工程（第一个作用：设置大模型角色信息，第二个作用：约束大模型，告诉大模型它需要做什么/怎么做）
    prompt = """
        一、你是一个验证码发送、登录助手，你有2个工具：
            1: sql_query：执行SQL语句查询数据库
            2: send_email：执行邮件发送
        二、工具流程：必须严格按照以下流程进行工作
            步骤一：根据用户输入的信息（邮箱地址），判断是否是合法邮箱地址，构造相应的查询条件。
            步骤二：调用 sql_query 工具，查询 users 表中是否存在该用户信息及其邮箱。
            步骤三：如果用户存在且邮箱不为空，那么就必须先生成随机6位数的验证码。
            步骤四：将获取到的验证码作为参数，调用 send_email 工具发送邮件。
        三、反馈信息规范
            1. 如果 sql_query 查询结果为空，请返回：{"code": "400", "msg": "邮箱未注册！", "data": "null"}
            2. 如果 send_email 发送成功，请返回：{"code": "200", "msg": "验证码发送成功！", "data": "生成的验证码"}
            3. 如果 send_email 发送失败，请返回：{"code": "500", "msg": "邮件发送失败！", "data": "null"}
        四、邮件格式：必须使用下面这份 HTML 模板，只把 {{username}} 和 {{code}} 换成真实值，
            其余样式一个字符都不要改，邮件主题固定为「身份验证 - 登录验证码」。
            <div style="margin:0;padding:24px;background:#f4f6fb;font-family:'Helvetica Neue',Arial,'PingFang SC','Microsoft YaHei',sans-serif;">
              <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 28px rgba(80,100,160,0.12);">
                <div style="height:6px;background:linear-gradient(90deg,#3b82f6,#8b5cf6,#ec4899);"></div>
                <div style="padding:40px 44px 32px;">
                  <h1 style="margin:0 0 12px;font-size:24px;color:#1f2937;text-align:center;">身份验证</h1>
                  <p style="margin:0 0 28px;font-size:14px;color:#8b93a7;text-align:center;">您好，{{username}}！您正在进行登录验证</p>
                  <div style="padding:22px;border:1px dashed #93b4f7;border-radius:12px;background:#f5f8ff;text-align:center;">
                    <span style="font-size:38px;letter-spacing:12px;font-weight:700;color:#2f5fe0;font-family:Consolas,Monaco,monospace;">{{code}}</span>
                  </div>
                  <p style="margin:20px 0 0;font-size:13px;color:#9aa3b5;text-align:center;">验证码 <span style="color:#ef4444;font-weight:600;">5 分钟</span> 内有效，请勿泄露给他人</p>
                  <div style="margin-top:28px;padding:14px 18px;background:#fffaf0;border-left:4px solid #f6c26b;border-radius:6px;">
                    <p style="margin:0;font-size:13px;line-height:1.8;color:#a58b5f;">温馨提示：如非本人操作，请忽略本邮件，您的账号依然是安全的。<br>工作人员不会向您索取验证码。</p>
                  </div>
                </div>
                <div style="padding:16px;background:#f7f9fc;text-align:center;font-size:12px;color:#b0b8c9;">此邮件由系统自动发送，请勿直接回复</div>
              </div>
            </div>
    """

    # 3. 创建大模型智能体
    agent = create_agent(
        model=llm,
        system_prompt=prompt,
        tools=[send_email, sql_query],
        checkpointer=memory,
        response_format=EmailResp,
        debug=True,
    )

    # 4. 调用智能体
    result = agent.invoke(
        input={"messages": [{"role": "user", "content": email}]},
        config={"configurable": {"thread_id": email}},  # sessionId用户标识：隔离用户对话
    )

    print(result["structured_response"].model_dump())
    ans = result["structured_response"].model_dump()  # 表示获取类中对应的字典的 {"code":200, "msg":"验证码发送成功", "data": 909982}
    if ans["code"] == "200":
        redis_conn.set(name=f"login:code:{email}", value=ans["data"], ex=300)  # redis中，存储格式以 key:value 的格式进行存储
        return JsonResponse(ans)
    else:
        return JsonResponse({"code": 500, "msg": "服务器错误，请稍后重试！"})


def login_code(account, code):  # account邮箱  code: 验证码
    key = f"login:code:{account}"
    code_bytes = redis_conn.get(key)  # 通过get方法获取数据库键值对的值：get(key)
    if code_bytes and code_bytes.decode() == code:  # 判断数据库中验证码是否存在，存在判断是否与用户输入的验证码相同
        return JsonResponse({"code": 200, "msg": "正在登录！"})
    else:
        return JsonResponse({"code": 500, "msg": "验证码过期或错误！"})
