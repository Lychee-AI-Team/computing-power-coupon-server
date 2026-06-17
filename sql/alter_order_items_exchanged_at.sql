-- 为 order_items 增加兑换时间字段.
-- NULL 表示未兑换, 非 NULL 表示兑换成功时间.

SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_items'
      AND COLUMN_NAME = 'exchanged_at'
);

SET @sql := IF(@col_exists = 0,
    'ALTER TABLE `order_items` ADD COLUMN `exchanged_at` DATETIME NULL DEFAULT NULL COMMENT ''兑换时间, NULL=未兑换'' AFTER `dispatched_at`',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
