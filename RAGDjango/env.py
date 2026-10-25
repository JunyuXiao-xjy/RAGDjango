"""环境变量加载与读取（项目内唯一的配置入口）。

设计目标：
1. 不引入额外依赖（不依赖 python-dotenv / django-environ）；
2. 所有敏感配置——Django SECRET_KEY、大模型 API Key、邮箱 SMTP 授权码、
   MySQL 口令——都通过「系统环境变量」或「项目根目录的 .env 文件」注入，
   代码里只保留键名和占位值，仓库中不会出现任何真实凭据。

用法::

    from . import env                 # 在 Django 应用包内部
    from RAGDjango import env         # 作为脚本直接运行时

    key = env.get("LLM_API_KEY")      # 取字符串，未配置时返回 None
    debug = env.get_bool("DJANGO_DEBUG", True)
    hosts = env.get_list("DJANGO_ALLOWED_HOSTS", ["127.0.0.1", "localhost"])
    port = env.get_int("DB_PORT", 3306)

.env 的书写格式见项目根目录的 .env.example。
"""
from __future__ import annotations

import os
from pathlib import Path

# 项目根目录（manage.py 所在目录），.env 就放在这里
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

_loaded = False


def load_env(path: Path | str | None = None) -> None:
    """把 .env 文件里的键值对读进 os.environ。

    已存在的系统环境变量优先级更高（不会被 .env 覆盖），便于生产环境注入。
    该函数只真正执行一次，重复调用无副作用。
    """
    global _loaded
    if _loaded:
        return
    _loaded = True

    env_path = Path(path) if path else ENV_FILE
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        # 跳过空行、注释行、以及不含 "=" 的非法行
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get(name: str, default: str | None = None) -> str | None:
    """读取字符串配置项；未配置或为空时返回 default。"""
    load_env()
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value


def get_bool(name: str, default: bool = False) -> bool:
    """读取布尔配置项，接受 1/true/yes/on（大小写不敏感）。"""
    value = get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_int(name: str, default: int) -> int:
    """读取整数配置项，解析失败时返回 default。"""
    raw = get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def get_list(name: str, default: list[str] | None = None) -> list[str]:
    """读取逗号分隔的列表配置项，例如 DJANGO_ALLOWED_HOSTS=a.com,b.com。"""
    raw = get(name)
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]
