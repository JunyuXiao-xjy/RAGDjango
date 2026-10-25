import json
import smtplib
import time
from email.mime.text import MIMEText

import MySQLdb
from langchain.tools import tool
from pydantic import BaseModel, Field

try:  # 作为包被导入时
    from ..env import get as env_get
except ImportError:  # 作为脚本直接运行时
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from RAGDjango.env import get as env_get

# ---------------------------------------------------------------------------
# 隐私占位：邮箱账号、SMTP 授权码、数据库口令全部改为从环境变量读取。
# 请复制 .env.example 为 .env 并填入你自己的值，不要把真实凭据写回源码。
#
# 数据库说明：这里的 MySQL 只存业务用户表 users（登录校验 / 按姓名查邮箱），
# 建表脚本见仓库根目录 sql/schema.sql；Django 自身的表仍在 SQLite，
# 由 `python manage.py migrate` 生成，不走这套连接。
# ---------------------------------------------------------------------------
MAIL_FROM = env_get("MAIL_FROM", "")            # 发件邮箱，例如 your_account@qq.com
MAIL_PASSWORD = env_get("MAIL_PASSWORD", "")    # 邮箱 SMTP 授权码（不是登录密码）
MAIL_SMTP_HOST = env_get("MAIL_SMTP_HOST", "smtp.qq.com")
MAIL_SMTP_PORT = int(env_get("MAIL_SMTP_PORT", "465"))

DB_CONFIG = {
    "host": env_get("DB_HOST", "127.0.0.1"),
    "port": int(env_get("DB_PORT", "3306")),
    "user": env_get("DB_USER", "root"),
    "passwd": env_get("DB_PASSWORD", ""),
    "database": env_get("DB_NAME", "rag"),
    "charset": "utf8mb4",
}



class EmailSchema(BaseModel):
    """send_email 工具的参数定义"""

    to: str = Field(..., description="收件人邮箱地址")
    subject: str = Field(..., description="邮件主题")
    content: str = Field(..., description="邮件正文内容（HTML 格式）")


@tool("send_email", args_schema=EmailSchema)
def send_email(to: str, subject: str, content: str) -> str:
    """发送邮件
    to: 收件人邮箱地址
    subject: 邮件主题
    content: 邮件正文内容（HTML 格式）
    """
    if not MAIL_FROM or not MAIL_PASSWORD:
        return (
            "邮件发送失败，失败原因：未配置发件邮箱。"
            "请在项目根目录的 .env 中填写 MAIL_FROM 与 MAIL_PASSWORD（SMTP 授权码）。"
        )

    try:
        # 创建邮件发送的对象（HTML + UTF-8 编码，避免中文乱码）
        text = MIMEText(content, _subtype="html", _charset="utf-8")
        text["to"] = to  # 设置收件人邮箱地址
        text["from"] = MAIL_FROM  # 自己的邮箱
        text["subject"] = subject

        # 创建 SMTP 邮箱对象，连接服务器发送邮件（QQ 服务器偶发 SSL EOF，重试 3 次）
        for attempt in range(1, 4):
            try:
                smtp = smtplib.SMTP_SSL(host=MAIL_SMTP_HOST, port=MAIL_SMTP_PORT, timeout=20)  # 通过SSL连接服务器
                smtp.login(user=MAIL_FROM, password=MAIL_PASSWORD)  # 登录QQ邮箱服务器
                smtp.sendmail(from_addr=MAIL_FROM, to_addrs=to, msg=text.as_string())  # 发送邮件
                smtp.quit()
                return f"邮件已成功发送给{to}"
            except Exception as e:
                if attempt == 3:
                    raise e
                time.sleep(2 * attempt)

        return f"邮件已成功发送给{to}"
    except Exception as e:
        return f"邮件发送失败，失败原因：{e}"


@tool("sql_query")
def sql_query(sql: str) -> str:
    """执行 SQL 查询语句，用于查询本系统的 users 用户表。

    users 表结构：
    - id INT，用户ID
    - username VARCHAR，用户姓名
    - email VARCHAR，用户邮箱
    - phone VARCHAR，用户电话
    - qq VARCHAR，用户QQ
    - birthday DATE，生日
    - created_at / updated_at TIMESTAMP，创建时间 / 更新时间
    - status TINYINT，状态：1-正常，0-禁用

    sql: 要执行的 SELECT 查询语句。例如根据邮箱查用户：
    SELECT id, username, email FROM users WHERE email = 'user@example.com';

    出于安全考虑，只允许执行 SELECT 查询语句，不要传入 INSERT / UPDATE / DELETE / DROP 等修改或破坏数据的语句。
    """
    stmt = sql.strip().rstrip(";").strip()
    if not stmt.lower().startswith("select"):
        return "数据库查询失败，失败原因：出于安全考虑，只允许执行 SELECT 查询语句"

    con = None
    try:
        con = MySQLdb.connect(**DB_CONFIG)
        with con.cursor() as cursor:
            cursor.execute(stmt)
            rows = cursor.fetchall()
            # description 必须在游标关闭前读取，用于拿到列名
            columns = [d[0] for d in (cursor.description or [])]
        con.commit()
        return _format_rows(rows, columns)
    except Exception as e:
        return f"数据库查询失败，失败原因：{e}"
    finally:
        if con is not None:
            con.close()


def _format_rows(rows, columns) -> str:
    """把查询结果转成便于大模型阅读的 JSON 文本。"""
    if not rows:
        return "[]"
    data = [dict(zip(columns, row)) for row in rows]
    return json.dumps(data, ensure_ascii=False, default=str)
