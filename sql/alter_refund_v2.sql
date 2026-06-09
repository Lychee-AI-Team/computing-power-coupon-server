-- 退款功能 v2 升级: 支持指定订单项退款 + 兑换码作废
-- 在已有库上执行

USE `computing_power_coupon-local`;

-- 1. order_items 表: exchange_status 注释新增 2=已退款
ALTER TABLE `order_items`
    MODIFY COLUMN `exchange_status` TINYINT NOT NULL DEFAULT 0
        COMMENT '兑换状态: 0=未兑换, 1=已兑换, 2=已退款';

-- 2. refunds 表: 增加 item_ids 和 disable_result 字段
ALTER TABLE `refunds`
    ADD COLUMN `item_ids` TEXT DEFAULT NULL COMMENT '本次退款关联的订单项ID列表(JSON)' AFTER `notify_payload`,
    ADD COLUMN `disable_result` TEXT DEFAULT NULL COMMENT '兑换码作废结果(JSON)' AFTER `item_ids`;
