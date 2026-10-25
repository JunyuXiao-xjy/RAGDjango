# RAGDjango

> 基于 Django + LangChain 的一站式 AI 演示项目：**基础聊天** / **RAG 法律问答** / **AI 邮件助手** / **邮箱验证码登录**。

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.1-092E20.svg)](https://www.djangoproject.com/)
[![LangChain](https://img.shields.io/badge/LangChain-1.4-1C3C3C.svg)](https://python.langchain.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ 功能特性

| 模块 | 路由 | 说明 |
| --- | --- | --- |
| 基础聊天 | `POST /api/chat/` | 流式对话（SSE），按 `sessionId` 隔离多轮上下文 |
| RAG 法律问答 | `POST /api/rag/` | 对《中华人民共和国刑法》做向量检索，Top-K 条文 + 大模型作答，回答标注条号 |
| AI 邮件助手 | `POST /api/email/` | Agent 工具调用：先查数据库拿收件人邮箱 → 生成邮件预览 → 用户确认后才真正发送 |
| 验证码登录 | `POST /send_code/`、`POST /login_code/` | 6 位验证码存 Redis（5 分钟过期），邮件模板化发送 |

其他：

- 前端为单文件 Vue 3 + ElementPlus（模板渲染，无构建步骤）；
- 向量库为「矩阵 + JSON」的极简实现（`numpy` 余弦相似度），无需外部向量数据库；
- 全部敏感配置通过环境变量注入，源码零凭据。

## 🧱 技术栈

- **后端**：Django 6.1、LangChain 1.4、LangGraph（Agent + 记忆）、OpenAI 兼容协议 SDK
- **检索**：`text-embedding-v3` 向量化 + `numpy` 余弦相似度，按「第 X 条」切分刑法条文
- **存储**：MySQL（用户表）、Redis（登录验证码）
- **前端**：Vue 3、ElementPlus、axios、marked

## 📁 目录结构

```
RAGDjango/
├── manage.py
├── requirements.txt
├── .env.example               # 配置模板（复制为 .env 后填写）
├── RAGDjango/
│   ├── settings.py            # 配置读取（SECRET_KEY/DEBUG/HOSTS 来自环境变量）
│   ├── env.py                 # 轻量 .env 加载器（无第三方依赖）
│   ├── llm.py                 # 大模型客户端（单例）
│   ├── urls.py / views.py     # 路由与视图（SSE 流式输出）
│   ├── service/auth.py        # 验证码发送与校验
│   ├── tools/
│   │   ├── ingest.py          # 离线：文档 → 切分 → 向量化 → 落盘
│   │   ├── rag.py             # 在线：检索 + 拼 prompt + 流式生成
│   │   ├── tools.py           # send_email / sql_query 两个 Agent 工具
│   │   └── vector_store/      # 生成的向量库（不入库，可重建）
│   └── doc/                   # RAG 数据源（刑法 docx）
├── templates/                 # index.html / login.html
└── static/                    # Vue、ElementPlus、样式、背景图
```

## 🚀 快速开始

### 1. 环境要求

- Python 3.12+
- MySQL 5.7+ / 8.x
- Redis 6+

### 2. 安装依赖

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
```

> `mysqlclient` 在 Windows 上若编译失败，可改用 `pip install pymysql` 并在
> `RAGDjango/__init__.py` 中添加 `pymysql.install_as_MySQLdb()`。

### 3. 配置（必做）

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

然后编辑 `.env`，至少填写：

| 变量 | 说明 |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django 密钥，用随机字符串（生成命令见 `.env.example`） |
| `LLM_API_KEY` / `LLM_BASE_URL` | 对话模型（任意 OpenAI 兼容网关） |
| `EMBED_API_KEY` / `EMBED_BASE_URL` | Embedding 模型，建库与检索共用 |
| `MAIL_FROM` / `MAIL_PASSWORD` | 发件邮箱与 **SMTP 授权码**（不是登录密码） |
| `DB_*` | MySQL 连接信息 |
| `REDIS_*` | Redis 连接信息 |

`.env` 已在 `.gitignore` 中，**不会被提交**。也可以直接用系统环境变量注入（优先级更高）。

### 4. 初始化数据库

```sql
CREATE DATABASE rag DEFAULT CHARACTER SET utf8mb4;

USE rag;
CREATE TABLE users (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  username    VARCHAR(64)  NOT NULL,
  email       VARCHAR(128) DEFAULT NULL,
  phone       VARCHAR(32)  DEFAULT NULL,
  qq          VARCHAR(32)  DEFAULT NULL,
  birthday    DATE         DEFAULT NULL,
  created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  status      TINYINT      DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

```bash
python manage.py migrate
```

### 5. 构建向量库（首次必做）

```bash
python -m RAGDjango.tools.ingest
```

产物写入 `RAGDjango/tools/vector_store/`：`embeddings.npy` + `chunks.json` + `meta.json`。
这些文件体积较大且可重建，因此**不纳入版本管理**。

### 6. 启动

```bash
python manage.py runserver
```

打开 <http://127.0.0.1:8000/>，用 `users` 表中已存在的邮箱接收验证码登录，登录后进入 `/index/`。

## 🔌 接口速览

```http
POST /api/chat/     {"question": "...", "sessionId": "user@example.com"}
POST /api/rag/      {"question": "故意杀人怎么判"}
POST /api/email/    {"question": "...", "sessionId": "user@example.com"}
POST /send_code/    {"email": "user@example.com"}
POST /login_code/   {"email": "user@example.com", "code": "123456"}
```

流式接口返回 `text/event-stream`，每帧格式为 `data: {"text": "..."}`，以 `data: [DONE]` 结束。

## 🖼️ 前端与美化

- 登录页背景图：`static/images/1.jpg`（仓库内的示例壁纸）。**建议替换成你自己用 AI 生成的图片**，保持文件名不变即可，无需改代码；
- 图标/配色集中在 `templates/login.html`、`templates/index.html` 的 `<style>` 中，可直接调整；
- 后端地址已改为相对路径（`/api/...`），换域名、换端口都不用改前端代码。

## 🔐 隐私与安全说明

发布前已对仓库做脱敏处理，源码中**不再包含任何真实凭据或个人信息**：

| 原内容 | 处理方式 |
| --- | --- |
| 模型网关 API Key（`sk-...`）及私有网关地址 | 删除，改为读取 `EMBED_API_KEY` / `EMBED_BASE_URL` / `LLM_API_KEY` / `LLM_BASE_URL` |
| Django `SECRET_KEY` | 删除，改为读取 `DJANGO_SECRET_KEY`（缺失时给出启动警告） |
| 邮箱账号 / SMTP 授权码 | 改为 `MAIL_FROM` / `MAIL_PASSWORD`，占位为空 |
| MySQL 用户名 / 口令 | 改为 `DB_USER` / `DB_PASSWORD`，并移除弱口令提示 |
| 示例中的真实 QQ 邮箱 | 替换为 `user@example.com` |
| 本机绝对路径（`E:/Anaconda/...`） | 替换为通用命令（`python -m ...`） |
| 本地 IDE 配置、聊天截图、向量库产物 | 加入 `.gitignore`，不进入仓库 |

**注意**

1. 请勿把 `.env` 提交到 Git；如果不小心提交过，除了删除文件，还要 **立即吊销并重新生成** 相关密钥。
2. `DEBUG` 默认由 `DJANGO_DEBUG` 控制，正式部署请设为 `False` 并配置 `DJANGO_ALLOWED_HOSTS`。
3. 本项目为教学/演示性质：`@csrf_exempt`、内存态会话（`InMemorySaver`）、允许 Agent 执行 SQL 等设计**不适合直接作为生产服务**，公网部署前请补充鉴权、限流与输入校验。

## 🤝 贡献

欢迎提 Issue / PR。提交前请确认：

- 没有把 `.env`、密钥、个人邮箱等隐私内容带进提交（`git diff --cached` 自查）；
- 新增的第三方依赖同步写入 `requirements.txt`。

## 📄 License

[MIT](LICENSE) © RAGDjango contributors
