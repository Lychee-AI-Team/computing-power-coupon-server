CREATE DATABASE IF NOT EXISTS `computing_power_coupon` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE `computing_power_coupon`;

CREATE TABLE IF NOT EXISTS `users` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `username` VARCHAR(50) NOT NULL,
    `password` VARCHAR(255) NOT NULL COMMENT 'bcrypt hash',
    `display_name` VARCHAR(100) NOT NULL,
    `role` VARCHAR(50) NOT NULL,
    `external_user_id` INT DEFAULT NULL COMMENT 'User ID from external platform',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_username` (`username`),
    KEY `idx_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `sku_config` (
    `sku_id` INT NOT NULL AUTO_INCREMENT,
    `sku_name` VARCHAR(100) NOT NULL COMMENT 'SKU名称',
    `face_value` DECIMAL(10, 2) NOT NULL COMMENT '面值',
    `bonus_amount` DECIMAL(10, 2) NOT NULL DEFAULT 0 COMMENT '赠送金额',
    `actual_amount` DECIMAL(10, 2) NOT NULL COMMENT '实际额度',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '上下架状态: 0=下架, 1=上架',
    `expire_type` VARCHAR(10) NOT NULL DEFAULT 'day' COMMENT '过期时间类型: day=天, month=月, year=年',
    `expire_value` INT NOT NULL DEFAULT 90 COMMENT '过期时间数量',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`sku_id`),
    KEY `idx_status` (`status`),
    KEY `idx_sku_name` (`sku_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `orders` (
    `order_id` INT NOT NULL AUTO_INCREMENT,
    `order_no` VARCHAR(64) NOT NULL COMMENT '订单号',
    `user_id` INT NOT NULL COMMENT '用户ID',
    `total_amount` DECIMAL(10, 2) NOT NULL COMMENT '订单总金额',
    `status` TINYINT NOT NULL DEFAULT 0 COMMENT '订单状态: 0=待支付, 1=已支付, 2=已取消, 3=已完成',
    `pay_channel` TINYINT DEFAULT NULL COMMENT '支付渠道: 1=微信, 2=支付宝',
    `transaction_id` VARCHAR(64) DEFAULT NULL COMMENT '微信支付交易号',
    `pay_info` TEXT DEFAULT NULL COMMENT '微信支付信息JSON',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`order_id`),
    UNIQUE KEY `uk_order_no` (`order_no`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `order_items` (
    `item_id` INT NOT NULL AUTO_INCREMENT,
    `order_id` INT NOT NULL COMMENT '订单ID',
    `sku_id` INT NOT NULL COMMENT 'SKU ID',
    `exchange_status` TINYINT NOT NULL DEFAULT 0 COMMENT '兑换状态: 0=未兑换, 1=已兑换',
    `exchange_user_id` INT DEFAULT NULL COMMENT '兑换用户ID',
    `expired_at` DATETIME DEFAULT NULL COMMENT '过期时间',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`item_id`),
    KEY `idx_order_id` (`order_id`),
    KEY `idx_sku_id` (`sku_id`),
    KEY `idx_exchange_user_id` (`exchange_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `cart_items` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `user_id` INT NOT NULL COMMENT '用户ID',
    `sku_id` INT NOT NULL COMMENT 'SKU ID',
    `quantity` INT NOT NULL DEFAULT 1 COMMENT '数量',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_user_sku` (`user_id`, `sku_id`),
    KEY `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
