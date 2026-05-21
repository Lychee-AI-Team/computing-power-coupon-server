# 算力券服务

算力券充值与管理系统的后端服务，基于 FastAPI 构建，支持用户注册登录、SKU 商品管理、购物车、订单创建、微信 Native 支付等完整业务流程。

## 技术栈

- **Web 框架**: FastAPI 0.115
- **异步 ORM**: SQLAlchemy 2.0 (asyncio)
- **数据库**: MySQL 8.0 (aiomysql)
- **缓存**: Redis 7
- **认证**: JWT (python-jose) + bcrypt
- **支付**: 微信支付 V3
- **部署**: Docker Compose

## 项目结构

```
├── app/
│   ├── api/                  # 路由层
│   │   ├── cart.py           # 购物车接口
│   │   ├── health.py         # 健康检查
│   │   ├── order.py          # 订单接口
│   │   ├── payment.py        # 支付接口
│   │   ├── sku.py            # SKU接口
│   │   └── user.py           # 用户接口
│   ├── core/                 # 核心配置
│   │   ├── auth.py           # 认证与权限
│   │   ├── config.py         # 环境配置
│   │   ├── database.py       # 数据库连接
│   │   ├── external_client.py# 外部平台客户端
│   │   ├── redis.py          # Redis连接
│   │   └── security.py       # 密码加密
│   ├── models/               # 数据模型
│   │   ├── cart.py           # 购物车模型
│   │   ├── order.py          # 订单模型
│   │   ├── sku.py            # SKU模型
│   │   └── user.py           # 用户模型
│   ├── schemas/              # 请求/响应模型
│   ├── services/             # 业务逻辑层
│   │   ├── cart_service.py   # 购物车服务
│   │   ├── order_service.py  # 订单服务
│   │   ├── sku_service.py    # SKU服务
│   │   ├── user_service.py   # 用户服务
│   │   └── wechat_pay_service.py # 微信支付服务
│   └── main.py               # 应用入口
├── sql/
│   └── init.sql              # 数据库初始化脚本
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── run.py                    # 启动脚本
```

## 快速开始

### 环境要求

- Python 3.13+
- MySQL 8.0+
- Redis 7+

### 本地开发

1. **克隆项目**

```bash
git clone https://github.com/Lychee-AI-Team/computing-power-coupon-server.git
cd computing-power-coupon-server
```

2. **创建环境配置**

```bash
cp .env.example .env
# 编辑 .env 填入实际的数据库、Redis、微信支付等配置
```

3. **安装依赖**

```bash
pip install -r requirements.txt
```

4. **初始化数据库**

执行 `sql/init.sql` 中的建表语句。

5. **微信支付证书**

将微信支付私钥和公钥文件放到项目根目录：
- `wechatpay_private_key.pem`
- `wechatpay_public_key.pem`

6. **启动服务**

```bash
python run.py
```

服务启动后访问 http://localhost:8888/docs 查看 Swagger API 文档。

### Docker 部署

```bash
docker-compose up -d --build
```

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MYSQL_HOST` | MySQL 主机 | 127.0.0.1 |
| `MYSQL_PORT` | MySQL 端口 | 3306 |
| `MYSQL_USER` | MySQL 用户名 | root |
| `MYSQL_PASSWORD` | MySQL 密码 | |
| `MYSQL_DATABASE` | 数据库名 | computing_power_coupon |
| `REDIS_HOST` | Redis 主机 | 127.0.0.1 |
| `REDIS_PORT` | Redis 端口 | 6379 |
| `REDIS_PASSWORD` | Redis 密码 | |
| `REDIS_DB` | Redis 数据库编号 | 0 |
| `APP_DEBUG` | 调试模式 | false |
| `APP_PORT` | 服务端口 | 8000 |
| `JWT_SECRET_KEY` | JWT 签名密钥 | change-me-in-production |
| `JWT_ALGORITHM` | JWT 算法 | HS256 |
| `JWT_EXPIRE_MINUTES` | JWT 过期时间(分钟) | 1440 |
| `WECHAT_APPID` | 微信 AppID | |
| `WECHAT_MCH_ID` | 微信商户号 | |
| `WECHAT_API_V3_KEY` | 微信支付 V3 密钥 | |
| `WECHAT_PRIVATE_KEY` | 微信支付私钥文件名 | |
| `WECHAT_MCH_SERIAL_NO` | 微信证书序列号 | |
| `WECHAT_PUBLIC_KEY` | 微信支付公钥文件名 | |
| `WECHAT_NOTIFY_URL` | 微信支付回调地址 | |
| `EXTERNAL_PLATFORM_BASE_URL` | 外部平台地址 | |
| `EXTERNAL_PLATFORM_ADMIN_TOKEN` | 外部平台令牌 | |
| `EXTERNAL_PLATFORM_ADMIN_ID` | 外部平台管理员ID | |

## API 接口

### 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |

### 用户管理

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/user/register` | 用户注册 | 否 |
| POST | `/api/user/login` | 用户登录 | 否 |
| GET | `/api/user/search` | 搜索用户 | 否 |
| PUT | `/api/user/password` | 修改密码 | 是 |
| POST | `/api/user/logout` | 用户登出 | 是 |

### SKU管理

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/sku/list` | SKU列表 | 管理员 |
| GET | `/api/sku/{sku_id}` | SKU详情 | 管理员 |
| POST | `/api/sku/create` | 创建SKU | 管理员 |
| PUT | `/api/sku/{sku_id}` | 更新SKU | 管理员 |
| DELETE | `/api/sku/{sku_id}` | 删除SKU | 管理员 |
| PUT | `/api/sku/{sku_id}/status` | 更新SKU状态 | 管理员 |

### 购物车

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/cart/add` | 添加到购物车 | 是 |
| GET | `/api/cart/list` | 购物车列表 | 是 |
| PUT | `/api/cart/{item_id}` | 修改数量 | 是 |
| DELETE | `/api/cart/{item_id}` | 删除购物车项 | 是 |
| DELETE | `/api/cart/clear/all` | 清空购物车 | 是 |

### 订单管理

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/order/create` | 创建订单（从购物车） | 是 |
| GET | `/api/order/my` | 我的订单列表 | 是 |
| GET | `/api/order/my/{order_id}` | 我的订单详情 | 是 |
| GET | `/api/order/admin/list` | 管理员-订单列表 | 管理员 |
| GET | `/api/order/admin/{order_id}` | 管理员-订单详情 | 管理员 |

### 支付管理

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/payment/native` | 微信Native支付 | 是 |
| POST | `/api/payment/notify` | 微信支付回调 | 否 |
| GET | `/api/payment/status/{order_id}` | 支付状态查询 | 是 |

## 业务流程

```
用户注册/登录 → 浏览SKU → 添加购物车 → 选择购物车项下单 → 微信扫码支付 → 支付完成
```

1. 用户注册并登录获取 JWT Token
2. 管理员创建 SKU 商品
3. 用户将 SKU 添加到购物车（支持数量累加）
4. 用户从购物车选择商品创建订单，系统自动删除已下单的购物车项
5. 调用微信 Native 支付接口获取扫码链接
6. 前端轮询支付状态，或微信服务器回调通知支付结果

## 数据库表

| 表名 | 说明 |
|------|------|
| `users` | 用户表 |
| `sku_config` | SKU商品配置表 |
| `cart_items` | 购物车表 |
| `orders` | 订单表 |
| `order_items` | 订单项表 |

## License

Private
