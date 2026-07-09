-- ============================================================
-- 版本: V_init
-- 分支: init (项目初始化)
-- 创建日期: 2026-05-21
-- 关联提交: 4a1592a init: 算力券服务项目初始提交 (后续多次累积更新至 d96dcb3)
-- 变更描述:
--   基线 schema 全量快照: 建库 + users / api_keys / sku_config /
--   orders / order_items / cart_items / refunds 七张表。
--   已合并所有历史 feature 分支的 schema 变更：
--     - feature/api-key: api_keys 表
--     - feature/wechat-refund: refunds.item_ids/disable_result, order_items.exchange_status 注释
--     - feature/external-interface: order_items.dispatched_at/exchanged_at + idx_order_dispatch
--     - feature/interface-order: orders.client_order_no, pay_channel 注释补 3=接口调用
-- 关联功能:
--   全服务基础表结构，对应 app/models/*.py
-- 幂等性: 是 (CREATE TABLE IF NOT EXISTS / CREATE DATABASE IF NOT EXISTS)
-- 执行方式:
--   全新部署执行本文件即可获得当前完整 schema。
--   以后的字段变动跟分支走，新增 V_<分支名>.sql 增量脚本。
-- ============================================================

CREATE DATABASE IF NOT EXISTS `computing_power_coupon` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE `computing_power_coupon`;

CREATE TABLE IF NOT EXISTS `users` (
    `id` INT NOT NULL COMMENT '第三方平台用户ID，与外部系统保持一致',
    `username` VARCHAR(50) NOT NULL COMMENT '用户名',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_username` (`username`),
    KEY `idx_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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

CREATE TABLE IF NOT EXISTS `sku_config` (
    `sku_id` INT NOT NULL AUTO_INCREMENT COMMENT 'SKU ID',
    `sku_name` VARCHAR(100) NOT NULL COMMENT 'SKU名称',
    `face_value` DECIMAL(10, 2) NOT NULL COMMENT '面值',
    `bonus_amount` DECIMAL(10, 2) NOT NULL DEFAULT 0 COMMENT '赠送金额',
    `actual_amount` DECIMAL(10, 2) NOT NULL COMMENT '实际额度',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '上下架状态: 0=下架, 1=上架',
    `expire_type` VARCHAR(10) NOT NULL DEFAULT 'day' COMMENT '过期时间类型: day=天, month=月, year=年',
    `expire_value` INT NOT NULL DEFAULT 90 COMMENT '过期时间数量',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`sku_id`),
    KEY `idx_status` (`status`),
    KEY `idx_sku_name` (`sku_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `orders` (
    `order_id` INT NOT NULL AUTO_INCREMENT COMMENT '订单ID',
    `order_no` VARCHAR(64) NOT NULL COMMENT '订单号',
    `user_id` INT NOT NULL COMMENT '用户ID',
    `total_amount` DECIMAL(10, 2) NOT NULL COMMENT '订单总金额',
    `status` TINYINT NOT NULL DEFAULT 0 COMMENT '订单状态: 0=待支付, 1=已支付, 2=已取消, 3=已完成, 4=已退款',
    `pay_channel` TINYINT DEFAULT NULL COMMENT '支付渠道: 1=微信, 2=支付宝, 3=接口调用',
    `transaction_id` VARCHAR(64) DEFAULT NULL COMMENT '微信支付交易号',
    `pay_info` TEXT DEFAULT NULL COMMENT '微信支付信息JSON',
    `client_order_no` VARCHAR(64) DEFAULT NULL COMMENT '客户侧订单号, 接口下单来源',
    `refunded_amount` DECIMAL(10, 2) NOT NULL DEFAULT 0 COMMENT '累计已退款金额',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`order_id`),
    UNIQUE KEY `uk_order_no` (`order_no`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `order_items` (
    `item_id` INT NOT NULL AUTO_INCREMENT COMMENT '订单项ID',
    `order_id` INT NOT NULL COMMENT '订单ID',
    `sku_id` INT NOT NULL COMMENT 'SKU ID',
    `exchange_status` TINYINT NOT NULL DEFAULT 0 COMMENT '兑换状态: 0=未兑换, 1=已兑换, 2=已退款',
    `exchange_user_id` INT DEFAULT NULL COMMENT '兑换用户ID',
    `expired_at` DATETIME DEFAULT NULL COMMENT '过期时间',
    `redemption_code` VARCHAR(128) DEFAULT NULL COMMENT '兑换码',
    `redemption_status` TINYINT NOT NULL DEFAULT 0 COMMENT '兑换码生成状态: 0=待生成, 1=生成中, 2=已生成, 3=生成失败',
    `dispatched_at` DATETIME DEFAULT NULL COMMENT '派发时间, NULL=未派发, 已派发后不可二次派发',
    `exchanged_at` DATETIME DEFAULT NULL COMMENT '兑换时间, NULL=未兑换',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`item_id`),
    KEY `idx_order_id` (`order_id`),
    KEY `idx_sku_id` (`sku_id`),
    KEY `idx_exchange_user_id` (`exchange_user_id`),
    KEY `idx_redemption_status` (`redemption_status`),
    KEY `idx_order_dispatch` (`order_id`, `dispatched_at`, `exchange_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `cart_items` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '购物车项ID',
    `user_id` INT NOT NULL COMMENT '用户ID',
    `sku_id` INT NOT NULL COMMENT 'SKU ID',
    `quantity` INT NOT NULL DEFAULT 1 COMMENT '数量',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_user_sku` (`user_id`, `sku_id`),
    KEY `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `refunds` (
    `refund_id` INT NOT NULL AUTO_INCREMENT COMMENT '退款记录ID',
    `refund_no` VARCHAR(64) NOT NULL COMMENT '商户退款单号',
    `order_id` INT NOT NULL COMMENT '订单ID',
    `order_no` VARCHAR(64) NOT NULL COMMENT '订单号',
    `refund_amount` DECIMAL(10, 2) NOT NULL COMMENT '本次退款金额(元)',
    `total_amount` DECIMAL(10, 2) NOT NULL COMMENT '订单原总额(元)',
    `reason` VARCHAR(255) DEFAULT NULL COMMENT '退款原因',
    `status` TINYINT NOT NULL DEFAULT 0 COMMENT '退款状态: 0=处理中, 1=成功, 2=失败, 3=异常',
    `wechat_refund_id` VARCHAR(64) DEFAULT NULL COMMENT '微信退款单号',
    `transaction_id` VARCHAR(64) DEFAULT NULL COMMENT '原支付交易号',
    `operator_id` INT NOT NULL COMMENT '操作管理员ID',
    `channel` TINYINT NOT NULL DEFAULT 1 COMMENT '退款渠道: 1=微信',
    `error_msg` TEXT DEFAULT NULL COMMENT '失败/异常原因',
    `notify_payload` TEXT DEFAULT NULL COMMENT '微信回调原始数据',
    `item_ids` TEXT DEFAULT NULL COMMENT '本次退款关联的订单项ID列表(JSON)',
    `disable_result` TEXT DEFAULT NULL COMMENT '兑换码作废结果(JSON)',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`refund_id`),
    UNIQUE KEY `uk_refund_no` (`refund_no`),
    KEY `idx_order_id` (`order_id`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
