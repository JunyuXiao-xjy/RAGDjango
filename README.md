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
├── sql/schema.sql             # MySQL 建库建表脚本（业务用户表 users）
├── templates/                 # index.html / login.html
└── static/                    # Vue、ElementPlus、样式、背景图
```

## 🗄️ 数据库与存储

项目里有 **三处存储**，职责完全不同，不要混淆：

| 存储 | 存什么 | 连接配置写在哪 | 怎么来 |
| --- | --- | --- | --- |
| **SQLite** `db.sqlite3` | Django 自身的 admin / session / auth 表 | `RAGDjango/settings.py` → `DATABASES` | `python manage.py migrate` 自动生成，**已 gitignore** |
| **MySQL** `rag.users` | 业务用户表：登录校验、邮件助手按姓名反查邮箱 | `.env` 的 `DB_*` → `RAGDjango/tools/tools.py` 的 `DB_CONFIG` | 手动执行 `sql/schema.sql` |
| **Redis** `login:code:{email}` | 登录验证码，TTL 300 秒 | `.env` 的 `REDIS_*` → `service/auth.py` | 启动 Redis 即可 |

> ⚠️ 常见的误解：`users` 表**不走 Django ORM**。`settings.py` 的 `DATABASES` 保持默认 SQLite 就好，
> 业务表由 `@tool("sql_query")` 通过 MySQLdb 直连查询，所以数据库账号密码配在 `.env` 的 `DB_*`。

### `users` 表字段（MySQL）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | INT PK | 自增主键 |
| `username` | VARCHAR(64) | 用户姓名，**邮件助手按这个字段反查邮箱** |
| `email` | VARCHAR(128) UNIQUE | 登录账号 + 默认收件地址，登录时必须命中 |
| `phone` / `qq` | VARCHAR | 联系方式，当前代码未使用 |
| `birthday` | DATE | 生日，当前代码未使用 |
| `created_at` / `updated_at` | TIMESTAMP | 自动维护 |
| `status` | TINYINT | 1-正常 / 0-禁用（**当前登录逻辑未强制校验**，需要时自行加判断） |

## 🚀 快速开始

### 1. 环境要求

- Python 3.12+
- MySQL 5.7+ / 8.x
- Redis 6+

### 2. 获取代码

```bash
git clone https://github.com/JunyuXiao-xjy/RAGDjango.git
cd RAGDjango
```

### 3. 安装依赖

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
```

> `mysqlclient` 在 Windows 上若编译失败，可改用 `pip install pymysql` 并在
> `RAGDjango/__init__.py` 中添加 `pymysql.install_as_MySQLdb()`。

### 4. 配置（必做）

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

### 5. 初始化数据库

**① 业务库（MySQL）** —— 执行仓库自带的脚本（或直接在 Navicat / Workbench 里运行 `sql/schema.sql`）：

```bash
mysql -u root -p < sql/schema.sql
```

**② 插入一个可登录的测试用户** —— 登录时会按 `email` 查这张表，表里没有对应邮箱就会返回「邮箱未注册！」：

```bash
mysql -u root -p rag -e "INSERT INTO users (username, email) VALUES ('测试用户', 'user@example.com');"
```

**③ Django 自身的表（SQLite）**：

```bash
python manage.py migrate
```

检查是否就绪：

```bash
mysql -u root -p -e "SELECT id, username, email FROM rag.users;"
python manage.py check
```

### 5.1 数据库常见报错

| 现象 | 原因与处理 |
| --- | --- |
| `(1045, "Access denied for user ...")` | `.env` 的 `DB_USER` / `DB_PASSWORD` 不对，或该账号没有 `rag` 库权限 |
| `(1146, "Table 'rag.users' doesn't exist")` | 没执行 `sql/schema.sql` |
| `(2003, "Can't connect to MySQL server on '127.0.0.1'")` | MySQL 服务未启动，或 `DB_PORT` 不是 3306 |
| 登录返回「邮箱未注册！」 | `users` 表里没有这条 email，先按上面第 ② 步插入 |
| 登录返回「验证码过期或错误！」 | Redis 未启动、验证码超过 5 分钟、或邮箱与发送时不一致 |
| `ModuleNotFoundError: No module named 'MySQLdb'` | 安装 `mysqlclient`；Windows 编译失败就装 `pymysql` 并按第 3 节的说明做别名 |
| `no such table: django_session` | 忘了执行 `python manage.py migrate` |

### 6. 构建向量库（首次必做）

```bash
python -m RAGDjango.tools.ingest
```

产物写入 `RAGDjango/tools/vector_store/`：`embeddings.npy` + `chunks.json` + `meta.json`。
这些文件体积较大且可重建，因此**不纳入版本管理**。

### 7. 启动

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
