"""大模型（对话）客户端。

隐私说明：API Key 与 API 地址已从源码中移除，改为从环境变量读取。
请在项目根目录的 .env 中配置（参考 .env.example）：

    LLM_API_KEY=你的密钥
    LLM_BASE_URL=https://你的网关地址/v1
    LLM_MODEL=qwen-max        # 可选，默认 qwen-max

兼容任何 OpenAI 协议网关（阿里云百炼 / DashScope / OpenAI / 本地 vLLM ...）。
"""
from langchain_openai import ChatOpenAI

import threading

from . import env


class ChatModel:
    _model = None

    _lock = threading.Lock()

    @classmethod
    def load_model_once(cls):
        if cls._model is None:
            with cls._lock:
                api_key = env.get("LLM_API_KEY")
                base_url = env.get("LLM_BASE_URL")

                if not api_key:
                    raise RuntimeError(
                        "未配置 LLM_API_KEY。请复制 .env.example 为 .env，"
                        "并填入你自己的模型 API Key 与地址。"
                    )

                cls._model = ChatOpenAI(
                    model=env.get("LLM_MODEL", "qwen-max"),
                    api_key=api_key,
                    base_url=base_url or None,  # 留空则使用 OpenAI 官方地址
                    temperature=0.8,
                    streaming=True,
                    extra_body={"thinking": {"type": "disabled"}},
                )
        return cls._model


if __name__ == "__main__":
    # 本地连通性自测：python -m RAGDjango.llm
    llm = ChatModel.load_model_once()
    result = llm.invoke("你好，请用一句话介绍一下你自己。")
    print(result.content)
