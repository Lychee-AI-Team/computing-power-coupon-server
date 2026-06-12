-- API Key 管理: 新建 api_keys 表
-- 在已有库上执行

USE `computing_power_coupon-local`;

CREATE TABLE IF NOT EXISTS `api_keys` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT 'API Key ID',
    `user_id` INT NOT NULL COMMENT '所属用户ID',
    `name` VARCHAR(64) NOT NULL COMMENT 'Key 名称',
    `key_prefix` VARCHAR(16) NOT NULL COMMENT '展示用前缀, sk_+前8位hex',
    `key_hash` VARCHAR(64) NOT NULL COMMENT 'Key SHA256 hex',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 0=禁用, 1=启用',
    `expired_at` DATETIME DEFAULT NULL COMMENT '过期时间, NULL=永不过期',
    `last_used_at` DATETIME DEFAULT NULL COMMENT '最近一次使用时间',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_key_hash` (`key_hash`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_status_expired` (`status`, `expired_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='API Key 管理表';
