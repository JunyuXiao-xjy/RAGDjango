-- =============================================================================
-- RAGDjango 业务库初始化脚本（MySQL 5.7+ / 8.x）
--
-- 用法：
--   mysql -u root -p < sql/schema.sql
--
-- 说明（重要）：
--   本脚本只负责「业务用户表 users」。
--   Django 自身的表（admin / session / auth）仍在 SQLite 的 db.sqlite3 中，
--   由 `python manage.py migrate` 自动生成，与这里的 MySQL 无关。
--
--   users 表不走 Django ORM，由 RAGDjango/tools/tools.py 里的
--   @tool("sql_query") 通过 MySQLdb 直接查询，所以连接参数写在 .env 的 DB_*，
--   而不是 settings.py 的 DATABASES。
-- =============================================================================

CREATE DATABASE IF NOT EXISTS `rag`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `rag`;

CREATE TABLE IF NOT EXISTS `users` (
  `id`         INT          NOT NULL AUTO_INCREMENT COMMENT '用户ID',
  `username`   VARCHAR(64)  NOT NULL                COMMENT '用户姓名（邮件助手按此字段反查邮箱）',
  `email`      VARCHAR(128) DEFAULT NULL            COMMENT '邮箱：登录账号 + 默认收件地址',
  `phone`      VARCHAR(32)  DEFAULT NULL            COMMENT '电话',
  `qq`         VARCHAR(32)  DEFAULT NULL            COMMENT 'QQ',
  `birthday`   DATE         DEFAULT NULL            COMMENT '生日',
  `created_at` TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                                        ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `status`     TINYINT      NOT NULL DEFAULT 1      COMMENT '状态：1-正常，0-禁用（当前登录逻辑未强制校验）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_users_email` (`email`),
  KEY `idx_users_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统用户表';

-- -----------------------------------------------------------------------------
-- 示例数据：登录时必须命中表里的 email，否则接口返回「邮箱未注册！」
-- 取消下面一行的注释即可插入一个测试用户
-- -----------------------------------------------------------------------------
-- INSERT INTO `users` (`username`, `email`) VALUES ('测试用户', 'user@example.com');

-- 验证是否插入成功
-- SELECT id, username, email, status FROM `users`;
