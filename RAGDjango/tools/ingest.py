"""
向量化代码（离线阶段）

职责：把 doc/ 目录下的文档 → 切分成块 → 向量化 → 落盘成本地"向量数据库"。

流程：
    文档(.docx) → 提取纯文本 → 递归切分(chunk) → Embedding API → embeddings.npy + chunks.json

运行：
    python -m RAGDjango.tools.ingest          # 在项目根目录执行
    # 或者
    python RAGDjango/tools/ingest.py

隐私说明：Embedding 的 API Key 与 API 地址已从源码中移除，
请在项目根目录的 .env 中配置（参考 .env.example）。

产物（存到 tools/vector_store/）：
    embeddings.npy  形状 (N, 1024) 的 float32 矩阵，每一行是一段文档的向量
    chunks.json     N 条记录，与 embeddings.npy 的行一一对应
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
from docx import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI

try:  # 作为包被导入时
    from ..env import get as env_get
except ImportError:  # 作为脚本直接运行时
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from RAGDjango.env import get as env_get

# ---------------------------------------------------------------- 配置

BASE_DIR = Path(__file__).resolve().parent.parent  # RAGDjango/
DOC_DIR = BASE_DIR / "doc"                        # 文档目录
STORE_DIR = Path(__file__).resolve().parent / "vector_store"  # 向量库落盘目录

# 隐私占位：Embedding 配置全部来自环境变量，源码中不含任何密钥
EMBED_API_KEY = env_get("EMBED_API_KEY")
EMBED_BASE_URL = env_get("EMBED_BASE_URL")
EMBED_MODEL = env_get("EMBED_MODEL", "text-embedding-v3")
EMBED_DIM = 1024

CHUNK_SIZE = 500      # 每块最大字符数
CHUNK_OVERLAP = 50    # 相邻块重叠字符数，避免切断语义
BATCH_SIZE = 10       # 单次请求最多 10 条（DashScope 限制 25 条/次，留余量）

client = None


def _get_client() -> OpenAI:
    """延迟创建 Embedding 客户端（缺少配置时给出明确提示）。"""
    global client
    if client is None:
        if not EMBED_API_KEY:
            raise RuntimeError(
                "未配置 EMBED_API_KEY。请复制 .env.example 为 .env，"
                "并填入你自己的 Embedding API Key 与地址。"
            )
        client = OpenAI(api_key=EMBED_API_KEY, base_url=EMBED_BASE_URL or None)
    return client


# 匹配「第X条」的边界（含 1~6 位中文数字），用于按条切分
ARTICLE_SPLIT_RE = re.compile(r"(?=第[一二三四五六七八九十百千零〇]{1,6}条)")
ARTICLE_NO_RE = re.compile(r"^(第[一二三四五六七八九十百千零〇]{1,6}条(?:之[一二三四五六七八九十]{1,3})?)")


def _article_no(text: str) -> str:
    """取出片段开头的条号，例如 '第二百三十二条'。"""
    m = ARTICLE_NO_RE.match(text.strip())
    return m.group(1) if m else ""


# ---------------------------------------------------------------- 1. 读取文档

def read_docx(path: Path) -> str:
    """从 .docx 提取纯文本（含表格）。"""
    doc = Document(str(path))
    parts = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            parts.append(text)

    # 刑法文档里的量刑表格也要收进来
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))

    return "\n".join(parts)


def load_documents() -> list[dict]:
    """读取 doc/ 下所有 .docx，返回 [{text, source}, ...]。"""
    docs = []
    if not DOC_DIR.exists():
        raise FileNotFoundError(f"文档目录不存在：{DOC_DIR}")

    for path in sorted(DOC_DIR.glob("*.docx")):
        if path.name.startswith("~$"):  # 跳过 Word 临时锁文件
            continue
        text = read_docx(path)
        if text.strip():
            docs.append({"text": text, "source": path.name})
            print(f"[读取] {path.name}  {len(text)} 字")

    if not docs:
        raise FileNotFoundError(f"{DOC_DIR} 下没有可用的 .docx 文件")
    return docs


# ---------------------------------------------------------------- 2. 切分

def split_documents(docs: list[dict]) -> list[dict]:
    """按「第X条」边界切分，超长条文再二次切。

    刑法文档结构规整，一条法条 = 一个语义单元。
    按条切分比按字数硬切精度高得多：检索"故意杀人"能直接命中第二百三十二条，
    而不是命中一堆相邻的、语义被稀释的条文。
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
        length_function=len,
    )

    chunks = []
    for doc in docs:
        # lookahead 分割：每段以「第X条」开头
        pieces = [p.strip() for p in ARTICLE_SPLIT_RE.split(doc["text"])]

        for piece in pieces:
            if len(piece) < 10:  # 丢掉"第一编 总则"这类标题碎片
                continue

            if len(piece) <= CHUNK_SIZE:
                chunks.append({"text": piece, "source": doc["source"]})
                continue

            # 超长条文（>500 字）二次切分，每块补上条号前缀，避免子块丢失归属
            prefix = _article_no(piece)
            for sub in splitter.split_text(piece):
                sub = sub.strip()
                if len(sub) < 10:
                    continue
                if prefix and not sub.startswith(prefix):
                    sub = f"{prefix} {sub}"
                chunks.append({"text": sub, "source": doc["source"]})

    print(f"[切分] 共 {len(chunks)} 个 chunk（按条切分，chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}）")
    return chunks


# ---------------------------------------------------------------- 3. 向量化

def embed_texts(texts: list[str]) -> np.ndarray:
    """批量调用 Embedding 接口，返回 (N, EMBED_DIM) 的矩阵。"""
    vectors = []
    total = len(texts)

    for start in range(0, total, BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        resp = _get_client().embeddings.create(model=EMBED_MODEL, input=batch)
        # 接口不保证顺序，按 index 排序
        batch_vecs = [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]
        vectors.extend(batch_vecs)
        print(f"[向量化] {min(start + BATCH_SIZE, total)}/{total}", end="\r")

    print()
    matrix = np.array(vectors, dtype=np.float32)
    print(f"[向量化] 完成，矩阵形状 {matrix.shape}")
    return matrix


# ---------------------------------------------------------------- 4. 落盘

def save_store(chunks: list[dict], embeddings: np.ndarray) -> None:
    """写入本地向量库（一个矩阵 + 一份元数据）。"""
    STORE_DIR.mkdir(parents=True, exist_ok=True)

    np.save(STORE_DIR / "embeddings.npy", embeddings)

    with open(STORE_DIR / "chunks.json", "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    meta = {
        "embedding_model": EMBED_MODEL,
        "dim": EMBED_DIM,
        "count": len(chunks),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }
    with open(STORE_DIR / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[落盘] {STORE_DIR}")
    print(f"       embeddings.npy  {embeddings.shape}")
    print(f"       chunks.json     {len(chunks)} 条")


# ---------------------------------------------------------------- 主流程

def main() -> None:
    print("=" * 56)
    print("RAG 离线向量化")
    print("=" * 56)

    docs = load_documents()
    chunks = split_documents(docs)
    embeddings = embed_texts([c["text"] for c in chunks])
    save_store(chunks, embeddings)

    print("=" * 56)
    print("完成。可以运行 rag.py 测试检索了。")


if __name__ == "__main__":
    sys.exit(main())
