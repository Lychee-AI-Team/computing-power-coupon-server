-- 为 order_items 增加派发标记字段, 用于"外部接口-未兑换券"派发逻辑.
-- NULL 表示未派发, 非 NULL 时间戳表示已派发, 已派发的 item 不可被外部接口二次派发.
-- 幂等执行: 重复运行不会报错.

SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_items'
      AND COLUMN_NAME = 'dispatched_at'
);

SET @sql := IF(@col_exists = 0,
    'ALTER TABLE `order_items` ADD COLUMN `dispatched_at` DATETIME NULL DEFAULT NULL COMMENT ''派发时间, NULL=未派发'' AFTER `redemption_status`',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_exists := (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_items'
      AND INDEX_NAME = 'idx_order_dispatch'
);

SET @sql := IF(@idx_exists = 0,
    'ALTER TABLE `order_items` ADD INDEX `idx_order_dispatch` (`order_id`, `dispatched_at`, `exchange_status`)',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
