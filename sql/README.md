# SQL 版本管理

本目录维护数据库 schema 的版本化 SQL 脚本。

## 版本规则

### 基线 + 分支增量

- **`V_init.sql` 是全量基线**：包含当前所有表的完整 CREATE 语句，已合并所有历史 feature 分支的 schema 变更。新部署只需执行此文件。
- **以后的字段变动跟分支走**：每在新分支上做 schema 变更，新增一个 `V_<分支名>.sql` 增量脚本。

### 文件命名

- 基线：`V_init.sql`（固定名，不随分支变）
- 增量：`V_<分支名>.sql`，分支名中的 `/` 替换为 `-`
  - 例：分支 `feature/api-key` -> `V_feature-api-key.sql`
  - 例：分支 `feature/interface-order` -> `V_feature-interface-order.sql`

### 文件头注释

每个 SQL 文件首部必须包含完整描述块：

```sql
-- ============================================================
-- 版本: V_<分支名>
-- 分支: <原分支名>
-- 创建日期: YYYY-MM-DD
-- 关联提交: <hash> <message>
-- 变更描述:
--   <这个版本做了什么，1-3 行>
-- 关联功能:
--   <app/xxx.py 或功能名>
-- 幂等性: 是/否
-- 执行方式:
--   <已有库执行一次 / 新部署无需执行 等>
-- ============================================================
```

## 当前文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `V_init.sql` | 基线 | 建库 + users / api_keys / sku_config / orders / order_items / cart_items / refunds 七张表的完整定义 |

## 执行方式

### 全新部署
执行 `V_init.sql` 即可获得当前完整 schema。

```bash
mysql -h <host> -P <port> -u <user> -p < db_name> < sql/V_init.sql
```

### 已有库升级
按版本文件列表中**尚未应用**的 `V_<分支名>.sql` 增量脚本执行。

## 新增版本流程（在新分支上做 schema 变更时）

1. 在新分支上创建 `V_<分支名>.sql`（分支名 `/` 替换为 `-`）。
2. 文件首部加完整注释块（按上方模板）。
3. **ALTER 必须幂等**：用 `information_schema.COLUMNS` / `STATISTICS` 检查存在性：
   ```sql
   SET @col_exists := (
       SELECT COUNT(*) FROM information_schema.COLUMNS
       WHERE TABLE_SCHEMA = DATABASE()
         AND TABLE_NAME = '<table>'
         AND COLUMN_NAME = '<column>'
   );
   SET @sql := IF(@col_exists = 0,
       'ALTER TABLE `<table>` ADD COLUMN ...',
       'SELECT 1');
   PREPARE stmt FROM @sql;
   EXECUTE stmt;
   DEALLOCATE PREPARE stmt;
   ```
4. **同步更新 `V_init.sql`**：把新字段/索引加到对应表定义里，保证全新部署一步到位。
5. 更新本 README 的"当前文件"列表。

## 注意事项

- **运行时不依赖本目录**：服务启动靠 `app/main.py` 的 `Base.metadata.create_all` 自动建表（不会 ALTER 已有表）。本目录仅供运维手动执行。
- **ORM 为单一事实源**：字段定义以 `app/models/*.py` 为准，schema 变更需同步改 ORM。
- **库名**：`V_init.sql` 用 `computing_power_coupon`；新脚本统一用 `DATABASE()` 或执行时显式 `USE`，避免写死库名。
