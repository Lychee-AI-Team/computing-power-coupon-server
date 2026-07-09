# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 本地启动（默认端口 8888，APP_DEBUG 控制热重载）
python run.py
# 或
uvicorn app.main:app --host 0.0.0.0 --port 8888 --reload

# Docker 部署（构建后镜像内不含 sql/ 目录变更，schema 改动需手动连库执行）
docker compose up -d --build app

# 运行测试（脚本式，非 pytest；直接调 service 层，不启 HTTP server）
python test_api_key.py
python test_refund.py

# 初始化数据库（仅新部署；已有库升级走 sql/ 下的增量脚本）
mysql -h <host> -P <port> -u <user> -p < db_name> < sql/V_init.sql
```

服务启动后 API 文档在 `http://localhost:8888/docs`（仅 `APP_DEBUG=true` 时开放）。

## 高层架构

### 三套鉴权机制（互不通用）

不同接口走不同鉴权，新增接口时按场景选择：

| 机制 | 头 | 入口依赖 | 适用场景 |
|---|---|---|---|
| JWT | `Authorization: Bearer <token>` | `get_current_user` / `require_admin` (`app/core/auth.py`) | 前端用户与管理员操作（登录态） |
| X-API-Key | `X-API-Key: sk_xxx` | `get_user_by_api_key` (`app/core/api_key_auth.py`) | M2M 接口（接口下单、外部券查询、外部订单查询） |
| X-Exchange-Token | `X-Exchange-Token: <ts>.<sig>` | `require_exchange_token` (`app/core/exchange_auth.py`) | 第三方平台回推兑换状态（HMAC-SHA256） |

- **角色只在 JWT payload 里**，User 模型无 role 字段。`ROLE_USER=1 / ROLE_ADMIN=10 / ROLE_SUPER_ADMIN=100`，admin 判定用 `require_admin`。
- JWT 有 Redis 黑名单（`token_blacklist:<token>`），登出时写入。
- X-API-Key 的明文不存库，存 SHA256 hash；明文仅创建时返回一次。
- X-Exchange-Token 是 HMAC 签名 token，密钥在 `EXCHANGE_API_SECRET_KEY`，可选过期（`EXCHANGE_TOKEN_MAX_AGE_SECONDS`，0=永久）。

### 订单与兑换码生命周期

订单状态机（`Order.status`）：
- `0` 待支付 → `1` 已支付（回调标记）/ `2` 已取消（超时或懒取消）
- `1` → `3` 已完成 / `4` 已退款

兑换码状态机（`OrderItem.redemption_status`）：
- `0` 待生成 → `1` 生成中 → `2` 已生成 / `3` 生成失败

**关键约束：兑换码生成必须异步**。微信支付回调有 5s 超时，回调内只做 `mark_order_paid` + `background_tasks.add_task(_generate_redemption_codes_task, ...)`，由后台任务逐条调第三方 `/api/redemption/` 生成。后台任务**必须用独立 DB session**（`async with async_session() as session`），不能复用请求 session（请求结束即关闭）。

`create_redemption_codes_for_order`（`app/services/order_service.py`）逐条行锁抢占：`SELECT ... WITH FOR UPDATE SKIP LOCKED WHERE redemption_status=0` → 标 `1` → 调第三方 → 成功标 `2` 写 code / 失败标 `3`，**逐条 commit**（避免部分失败丢失）。失败的 `3` 留给补偿任务，不回滚已成功的。

### 接口下单（绕过支付）

`POST /api/interface/order/create`（`app/api/interface_order.py`）是特殊路径：
- 创建订单时直接 `status=1, pay_channel=3`，不走支付
- 立即返回 `order_no`，兑换码后台异步生成
- 查询用 `GET /api/interface/order/status?user_id=..&client_order_no=..`，按 `(user_id, client_order_no)` 查（业务上需保证唯一）
- **白名单门禁**：`INTERFACE_ORDER_ALLOWED_USER_IDS`（逗号分隔的 user_id）配置在 `.env`，不在白名单的 user 返回 403
- 聚合状态：任一 item `redemption_status=3` → `failed`；全部 `=2` → `success`（返回 codes）；其余 → `generating`

### ExternalPlatformService 的双 client 策略

`app/services/external_platform.py` 调第三方平台（`EXTERNAL_PLATFORM_BASE_URL`）：
- **全局 admin client**（`app/core/external_client.py` 的 `external_client`）：带 admin token，用于创建兑换码、改密码等。所有 admin 调用共享此 client。
- **一次性 client**（方法内 `httpx.AsyncClient`）：用于 login / wechat_qrcode / wechat_scan_login 等**会被第三方下发 session cookie 的接口**。如果用全局 client，session cookie 会污染 admin 调用的身份。

新增第三方接口时，判断是否会下发 cookie：会则用一次性 client，不会则用全局 client。

### 限流

`app/core/rate_limit.py` 的 `check_rate_limit(key, max_requests, window)` 用 Redis Lua 脚本（`INCR` + 首次 `EXPIRE`）保证原子性，超限抛 `429`。通常按 `key`（API Key id）+ `ip` 双维度限流。Key 命名规范：`rate_limit:<业务>:<维度>:<标识>`。

### 数据库 schema 管理

- **运行时**：`app/main.py` lifespan 里 `Base.metadata.create_all` 自动建表（按 `app/models/*.py` 的 ORM 定义），**不会 ALTER 已有表**。
- **schema 变更**：必须手动执行 `sql/` 下的 SQL 脚本。ORM 是单一事实源，SQL 脚本要与 ORM 一致。

详见下方"SQL 变更规则"。

### 魔法数与约定

- 兑换码额度：`quota = int(sku.actual_amount * 500000)`（`create_redemption_codes_for_order`）
- 订单号：`uuid.uuid4().hex[:16].upper()`
- 订单支付超时：`ORDER_PAYMENT_TIMEOUT_MINUTES = 10`（`app/services/order_service.py`），调度任务每分钟扫一次 + 查询时懒取消，用 DB 端 `NOW()` 判断避免时区问题
- 微信支付证书：`wechatpay_private_key.pem` / `wechatpay_public_key.pem` 放项目根目录

## SQL 变更规则（重要）

涉及数据库 schema 变更时，必须按 `sql/README.md` 的版本管理规则处理。核心要点：

### 结构
- `sql/V_init.sql` 是**全量基线**：包含当前所有表的完整 CREATE 语句。新部署只跑此文件。
- 以后的字段变动**跟分支走**：每个做 schema 变更的分支新增一个 `V_<分支名>.sql` 增量脚本。

### 命名
- 基线固定名：`V_init.sql`
- 增量：`V_<分支名>.sql`，分支名中的 `/` 替换为 `-`
  - 例：`feature/api-key` -> `V_feature-api-key.sql`

### 文件头注释（每个 SQL 文件必须有）
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

### 新增版本流程
1. 在新分支上创建 `V_<分支名>.sql`。
2. 加文件头注释块。
3. **ALTER 必须幂等**：用 `information_schema.COLUMNS` / `STATISTICS` 检查存在性（参考下方模板），禁止裸 `ALTER TABLE ADD COLUMN`。
4. **同步更新 `V_init.sql`**：把新字段/索引加到对应表定义里，保证全新部署一步到位。
5. 更新 `sql/README.md` 的"当前文件"列表。

### 幂等 ALTER 模板
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

### 关键约束
- **ORM 为单一事实源**：字段定义以 `app/models/*.py` 为准，schema 变更必须同步改 ORM。
- **运行时不依赖 `sql/` 目录**：`Base.metadata.create_all` 自动建表但不会 ALTER，SQL 脚本仅供运维手动执行。
- **库名不写死**：新脚本统一用 `DATABASE()` 或执行时显式 `USE`。
- **新增字段必须同时改两处**：ORM 模型 + SQL 脚本（`V_init.sql` 基线 + `V_<分支名>.sql` 增量）。

详见 `sql/README.md`。
