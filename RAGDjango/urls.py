"""
URL configuration for RAGDjango project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""

from django.contrib import admin
from django.urls import path

from .views import *

# path 路由地址，前端访问的URL请求地址，比如 www.baidu.com/图片
# 路由的语法格式：path("请求路径/", views中的将要访问的方法, name="就是这个路由的名称")
# 如果在前端访问路由执行对应的方法：启动服务器 127.0.0.1:8000/请求路径?行参变量 -> 后端需要接收的值

urlpatterns = [
    # </admin/>
    path(route='admin/', view=admin.site.urls),

    # </send_email/>
    path(route="send_email/", view=send_email_assistant, name="邮件发送助手！"),

    # 项目代码
    # </>  :默认请求地址 127.0.0.1:8000
    path(route="", view=login_html, name="访问登录页面!"),  # "" :默认请求地址 127.0.0.1:8000

    # </index/>
    path(route="index/", view=index_html, name="主页面"),  # http://127.0.0.1:8000/index/

    # 发送验证码的路由
    # </send_code/>
    path(route="send_code/", view=send_code, name="验证码发送！"),

    # 验证码登录的路由
    # </login_code/>
    path("login_code/", login_code, name="验证码登录功能！"),

    # 邮件发送的路由
    # </api/email/>
    path("api/email/", send_email_assis, name="流式邮件发送"),

    # 基础聊天模型
    # </api/chat/>
    path("api/chat/", api_chat, name="基础聊天模型"),

    # RAG 向量增强检索
    # </api/rag/>
    path("api/rag/", api_rag, name="RAG向量检索"),
]
