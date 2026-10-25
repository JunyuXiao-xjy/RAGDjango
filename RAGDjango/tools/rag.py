"""
向量增强检索代码（在线阶段）

职责：用户提问 → 向量化 → 在向量库里找最相似的文档 → 拼进 prompt → 大模型作答。

流程：
    问题("什么是故意杀人")
        → Embedding → 向量 [0.12, -0.03, ...]
        → 与 embeddings.npy 每一行算余弦相似度
        → 取 Top-K 最相似的 chunk
        → 反序列化成文本，塞进 prompt
        → 大模型基于这些条文生成答案

依赖：先运行 ingest.py 建好向量库（tools/vector_store/）。

隐私说明：Embedding 的 API Key 与 API 地址已从源码中移除，
请在项目根目录的 .env 中配置 EMBED_API_KEY / EMBED_BASE_URL / EMBED_MODEL
（参考 .env.example 与 README 的「本地配置」一节）。

单独测试：
    python -m RAGDjango.tools.rag
"""

import json
import sys
from pathlib import Path
from typing import Iterator

import numpy as np
from langchain.tools import tool
from openai import OpenAI

try:  # 作为包被导入时（Django 运行时）
    from ..env import get as env_get
except ImportError:  # 作为脚本直接运行时
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from RAGDjango.env import get as env_get

# ---------------------------------------------------------------- 配置

STORE_DIR = Path(__file__).resolve().parent / "vector_store"

# 隐私占位：以下三项均从环境变量读取，源码中不再出现真实密钥与私有网关地址
EMBED_API_KEY = env_get("EMBED_API_KEY")
EMBED_BASE_URL = env_get("EMBED_BASE_URL")
EMBED_MODEL = env_get("EMBED_MODEL", "text-embedding-v3")

TOP_K = 4  # 默认召回条数

_client = None


def _get_client() -> OpenAI:
    """延迟创建 Embedding 客户端（缺少配置时给出明确提示）。"""
    global _client
    if _client is None:
        if not EMBED_API_KEY:
            raise RuntimeError(
                "未配置 EMBED_API_KEY。请复制 .env.example 为 .env，"
                "并填入你自己的 Embedding API Key 与地址。"
            )
        _client = OpenAI(api_key=EMBED_API_KEY, base_url=EMBED_BASE_URL or None)
    return _client


# 向量库缓存：(归一化后的矩阵, chunk 列表)，进程内只加载一次
_index = None


# ---------------------------------------------------------------- 向量库加载

def _load_index():
    """加载 embeddings.npy + chunks.json，矩阵预先做 L2 归一化。"""
    global _index
    if _index is None:
        emb_path = STORE_DIR / "embeddings.npy"
        chunks_path = STORE_DIR / "chunks.json"

        if not emb_path.exists() or not chunks_path.exists():
            raise FileNotFoundError(
                f"向量库不存在：{STORE_DIR}\n请先运行：python RAGDjango/tools/ingest.py"
            )

        matrix = np.load(emb_path).astype(np.float32)
        with open(chunks_path, "r", encoding="utf-8") as f:
            chunks = json.load(f)

        # 归一化后，点积 == 余弦相似度
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        _index = (matrix / norms, chunks)

    return _index


def is_index_ready() -> bool:
    """向量库是否已构建。"""
    return (STORE_DIR / "embeddings.npy").exists() and (STORE_DIR / "chunks.json").exists()


# ---------------------------------------------------------------- 检索

def _embed_query(query: str) -> np.ndarray:
    """把问题向量化，并归一化。"""
    resp = _get_client().embeddings.create(model=EMBED_MODEL, input=[query])
    vec = np.array(resp.data[0].embedding, dtype=np.float32)
    norm = np.linalg.norm(vec) or 1.0
    return vec / norm


def search(query: str, top_k: int = TOP_K) -> list[dict]:
    """在向量库里检索与 query 最相似的 top_k 个文档块。

    返回：[{"text": 片段, "source": 文件名, "score": 相似度}, ...]
    """
    matrix, chunks = _load_index()
    scores = matrix @ _embed_query(query)          # (N,) 余弦相似度
    top_idx = np.argsort(scores)[::-1][:top_k]

    return [
        {
            "text": chunks[i]["text"],
            "source": chunks[i].get("source", ""),
            "score": float(scores[i]),
        }
        for i in top_idx
    ]


# ---------------------------------------------------------------- Prompt 组装

SYSTEM_PROMPT = """你是一名严谨的法律问答助手，精通《中华人民共和国刑法》。
必须遵守以下规则：
1. 只依据【参考资料】中的条文作答，不得编造法条编号或条文内容；
2. 回答时标注所引用的条号，例如"根据《刑法》第二百三十二条"；
3. 如果参考资料不足以回答，明确说明"现有资料未涵盖该问题"，再给出最接近的相关条文；
4. 先给结论，再给法律依据，最后用通俗语言解释；
5. 不要输出 JSON，不要自称"我是一个AI模型"。"""

USER_TEMPLATE = """【参考资料】
{context}

【用户问题】
{question}

请基于上述参考资料回答。"""


def build_prompt(question: str, docs: list[dict]) -> str:
    """把检索到的文档块拼成 prompt 正文。"""
    context = "\n\n".join(
        f"[{i + 1}] 来源：{d['source']}（相似度 {d['score']:.3f}）\n{d['text']}"
        for i, d in enumerate(docs)
    )
    return USER_TEMPLATE.format(context=context, question=question)


def _get_llm():
    """复用 llm.py 里的模型单例。"""
    try:
        from ..llm import ChatModel          # 作为包被导入时（Django 运行时）
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from RAGDjango.llm import ChatModel  # 作为脚本直接运行时
    return ChatModel.load_model_once()


# ---------------------------------------------------------------- 对外接口

def rag_stream(question: str, top_k: int = TOP_K) -> Iterator[str]:
    """流式版：逐 token 产出答案，供 views.py 的 SSE 使用。"""
    docs = search(question, top_k)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt(question, docs)},
    ]
    for chunk in _get_llm().stream(messages):
        if chunk.content:
            yield chunk.content


def rag_answer(question: str, top_k: int = TOP_K) -> dict:
    """非流式版：返回 {answer, sources}。"""
    docs = search(question, top_k)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt(question, docs)},
    ]
    result = _get_llm().invoke(messages)
    return {
        "answer": result.content,
        "sources": [{"source": d["source"], "score": d["score"]} for d in docs],
    }


@tool("search_law")
def search_law(query: str) -> str:
    """检索《中华人民共和国刑法》条文，用于回答法律问题。

    query: 用户的自然语言问题，例如"故意杀人怎么判"。
    返回与问题最相关的若干条文片段（JSON 字符串）。
    """
    try:
        docs = search(query)
        return json.dumps(docs, ensure_ascii=False)
    except Exception as e:
        return f"检索失败，失败原因：{e}"


# ---------------------------------------------------------------- 自测

if __name__ == "__main__":
    print("=" * 56)
    if not is_index_ready():
        print(f"向量库不存在：{STORE_DIR}")
        print("请先运行：python -m RAGDjango.tools.ingest")
        sys.exit(1)

    question = "什么是故意杀人罪？怎么判？"
    print(f"问题：{question}")
    print("=" * 56)

    hits = search(question, top_k=3)
    for i, h in enumerate(hits, 1):
        print(f"\n--- 召回 {i}  相似度 {h['score']:.4f} ---")
        print(h["text"][:220].replace("\n", " "))

    print("\n" + "=" * 56)
    print("大模型回答：")
    print("=" * 56)
    for token in rag_stream(question):
        print(token, end="", flush=True)
    print()
