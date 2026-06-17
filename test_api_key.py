"""
API Key 管理功能完整测试
- 直接调用 ApiKeyService 与鉴权依赖, 不启 HTTP server
- 覆盖: CRUD, 哈希存储, 隔离, 鉴权各种边界, last_used_at, 未兑换券查询过滤
"""
import asyncio
import hashlib
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text

from app.core.api_key_auth import get_user_by_api_key
from app.core.database import async_session
from app.models.api_key import ApiKey
from app.services.api_key_service import _UNSET, ApiKeyService


# ── helpers ─────────────────────────────────────────────────────────

USER_A = 13   # grey_test
USER_B = 14   # grey_test2

# 准备一个独立的测试 sku 与若干 order/order_item, 完全用 9xx 区段避免冲突
SKU_ID = 9001
ORDER_BASE = 9100  # 9100..9104
ITEM_BASE = 9200   # 9200..9210

passed = 0
failed = 0


def report(name: str, ok: bool, detail: str = ""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} — {detail}")


async def setup_data(db):
    """清理并准备测试数据."""
    # 清理本测试用到的所有数据
    await db.execute(text("DELETE FROM api_keys WHERE user_id IN (:a, :b)"),
                     {"a": USER_A, "b": USER_B})
    await db.execute(text("DELETE FROM order_items WHERE order_id BETWEEN :s AND :e"),
                     {"s": ORDER_BASE, "e": ORDER_BASE + 99})
    await db.execute(text("DELETE FROM orders WHERE order_id BETWEEN :s AND :e"),
                     {"s": ORDER_BASE, "e": ORDER_BASE + 99})
    await db.execute(text("DELETE FROM sku_config WHERE sku_id = :s"), {"s": SKU_ID})

    # SKU
    await db.execute(text("""
        INSERT INTO sku_config (sku_id, sku_name, face_value, bonus_amount, actual_amount,
                                status, expire_type, expire_value)
        VALUES (:sku_id, 'TEST_SKU', 100.00, 0, 100.00, 1, 'day', 90)
    """), {"sku_id": SKU_ID})

    # Orders: 9100=USER_A 已支付(1), 9101=USER_A 已完成(3), 9102=USER_A 待支付(0),
    #         9103=USER_A 已退款(4), 9104=USER_B 已支付(1)
    await db.execute(text("""
        INSERT INTO orders (order_id, order_no, user_id, total_amount, status,
                            pay_channel, transaction_id, refunded_amount)
        VALUES
          (:o1, 'TKO_9100', :ua, 100.00, 1, 1, 'WX_9100', 0),
          (:o2, 'TKO_9101', :ua, 100.00, 3, 1, 'WX_9101', 0),
          (:o3, 'TKO_9102', :ua, 100.00, 0, 1, NULL,      0),
          (:o4, 'TKO_9103', :ua, 100.00, 4, 1, 'WX_9103', 100.00),
          (:o5, 'TKO_9104', :ub, 100.00, 1, 1, 'WX_9104', 0)
    """), {
        "o1": ORDER_BASE, "o2": ORDER_BASE + 1, "o3": ORDER_BASE + 2,
        "o4": ORDER_BASE + 3, "o5": ORDER_BASE + 4,
        "ua": USER_A, "ub": USER_B,
    })

    future = datetime.now() + timedelta(days=30)
    past = datetime.now() - timedelta(days=1)

    # OrderItems:
    # 9200: order 9100 (paid) 未兑换 + 有码 + 未过期 → 应出现
    # 9201: order 9100 (paid) 已兑换 → 不应出现
    # 9202: order 9100 (paid) 未兑换 + 没码 → 不应出现
    # 9203: order 9100 (paid) 未兑换 + 有码 + 已过期 → 不应出现
    # 9204: order 9101 (completed) 未兑换 + 有码 + 永不过期 → 应出现
    # 9205: order 9102 (待支付)   未兑换 + 有码 → 不应出现
    # 9206: order 9103 (已退款)   未兑换 + 有码 → 不应出现 (status=4 不在 [1,3])
    # 9207: order 9104 (USER_B paid) 未兑换 + 有码 → USER_A 看不到
    rows = [
        (ITEM_BASE + 0, ORDER_BASE,     SKU_ID, 0, "CODE_USERA_001", future),
        (ITEM_BASE + 1, ORDER_BASE,     SKU_ID, 1, "CODE_USERA_USED", future),
        (ITEM_BASE + 2, ORDER_BASE,     SKU_ID, 0, None,             future),
        (ITEM_BASE + 3, ORDER_BASE,     SKU_ID, 0, "CODE_USERA_EXP", past),
        (ITEM_BASE + 4, ORDER_BASE + 1, SKU_ID, 0, "CODE_USERA_002", None),
        (ITEM_BASE + 5, ORDER_BASE + 2, SKU_ID, 0, "CODE_USERA_PEND", future),
        (ITEM_BASE + 6, ORDER_BASE + 3, SKU_ID, 0, "CODE_USERA_RFND", future),
        (ITEM_BASE + 7, ORDER_BASE + 4, SKU_ID, 0, "CODE_USERB_001", future),
    ]
    for r in rows:
        await db.execute(text("""
            INSERT INTO order_items (item_id, order_id, sku_id, exchange_status, redemption_code, expired_at)
            VALUES (:i, :o, :s, :ex, :c, :e)
        """), {"i": r[0], "o": r[1], "s": r[2], "ex": r[3], "c": r[4], "e": r[5]})
    await db.commit()


async def cleanup_data(db):
    await db.execute(text("DELETE FROM api_keys WHERE user_id IN (:a, :b)"),
                     {"a": USER_A, "b": USER_B})
    await db.execute(text("DELETE FROM order_items WHERE order_id BETWEEN :s AND :e"),
                     {"s": ORDER_BASE, "e": ORDER_BASE + 99})
    await db.execute(text("DELETE FROM orders WHERE order_id BETWEEN :s AND :e"),
                     {"s": ORDER_BASE, "e": ORDER_BASE + 99})
    await db.execute(text("DELETE FROM sku_config WHERE sku_id = :s"), {"s": SKU_ID})
    await db.commit()


async def run_tests():
    async with async_session() as db:
        svc = ApiKeyService(db)

        # ──── 数据准备 ────
        await setup_data(db)
        print("=== 数据准备完成 ===")

        # ──── 测试 1: 创建 ApiKey ────
        print("\n【测试 1】创建 API Key")
        ak1, raw1 = await svc.create(USER_A, "key1", expired_at=None)
        report("返回 raw_key 非空", bool(raw1) and raw1.startswith("sk_"))
        report("raw_key 长度 = 35", len(raw1) == 35)
        report("key_prefix = sk_+8位", ak1.key_prefix == raw1[:11])
        report("key_hash = sha256(raw)", ak1.key_hash == hashlib.sha256(raw1.encode()).hexdigest())
        report("初始 status=1", ak1.status == 1)
        report("初始 expired_at is None", ak1.expired_at is None)
        report("初始 last_used_at is None", ak1.last_used_at is None)
        ak1_id = ak1.id
        ak1_raw = raw1

        # ──── 测试 2: 创建第二个带过期时间的 key ────
        print("\n【测试 2】创建带 expired_at 的 Key")
        future = datetime.now() + timedelta(days=7)
        ak2, raw2 = await svc.create(USER_A, "key2", expired_at=future)
        report("expired_at 持久化", ak2.expired_at is not None)
        ak2_id = ak2.id

        # ──── 测试 3: 不同 raw_key 哈希不同 ────
        print("\n【测试 3】不同 Key 哈希不冲突")
        report("两次生成 raw_key 不同", raw1 != raw2)
        report("两次哈希值不同", ak1.key_hash != ak2.key_hash)

        # ──── 测试 4: 列表(只看本人) ────
        print("\n【测试 4】列表仅返回本人")
        ak_b, raw_b = await svc.create(USER_B, "key_b", expired_at=None)
        items_a, total_a = await svc.list_keys(USER_A, page=1, page_size=20)
        items_b, total_b = await svc.list_keys(USER_B, page=1, page_size=20)
        report("USER_A 总数=2", total_a == 2)
        report("USER_B 总数=1", total_b == 1)
        report("USER_A 列表不含 B 的 key", all(it.user_id == USER_A for it in items_a))
        report("按 id desc 排序", items_a[0].id > items_a[1].id)

        # ──── 测试 5: get 校验归属 ────
        print("\n【测试 5】get 校验归属")
        ak_owned = await svc.get(ak1_id, USER_A)
        ak_foreign = await svc.get(ak1_id, USER_B)
        report("本人可获取", ak_owned is not None and ak_owned.id == ak1_id)
        report("他人取不到", ak_foreign is None)

        # ──── 测试 6: update 局部更新 ────
        print("\n【测试 6】update 仅更新传入字段")
        old_name = ak1.name
        old_status = ak1.status
        old_expired = ak1.expired_at
        updated = await svc.update(ak1_id, USER_A, name="renamed")
        report("name 已更新", updated.name == "renamed")
        report("status 未动", updated.status == old_status)
        report("expired_at 未动", updated.expired_at == old_expired)

        # 改 status
        updated = await svc.update(ak1_id, USER_A, status_=0)
        report("status 已改为 0", updated.status == 0)
        # 恢复
        await svc.update(ak1_id, USER_A, status_=1)

        # 改 expired_at: 显式 sentinel 设值
        new_expire = datetime.now() + timedelta(days=1)
        updated = await svc.update(ak1_id, USER_A, expired_at=new_expire)
        report("expired_at 已更新", updated.expired_at is not None)
        # 重置为 None (显式传 None)
        updated = await svc.update(ak1_id, USER_A, expired_at=None)
        report("expired_at 重置为 None", updated.expired_at is None)
        # _UNSET 应不修改 expired_at: 先设为 None 后再用 _UNSET
        updated = await svc.update(ak1_id, USER_A, expired_at=new_expire)
        kept_expired = updated.expired_at
        updated = await svc.update(ak1_id, USER_A, name="renamed_again")  # 默认 _UNSET
        report("_UNSET 不修改 expired_at", updated.expired_at == kept_expired)
        # 清理: 改回永不过期
        await svc.update(ak1_id, USER_A, expired_at=None)

        # 他人无法 update
        not_found = await svc.update(ak1_id, USER_B, name="hacked")
        report("他人 update 返回 None", not_found is None)

        # ──── 测试 7: get_by_raw_key ────
        print("\n【测试 7】get_by_raw_key 走哈希索引")
        found = await svc.get_by_raw_key(ak1_raw)
        report("正确 raw_key 命中", found is not None and found.id == ak1_id)
        not_found = await svc.get_by_raw_key("sk_invalid_abc123")
        report("错误 raw_key 不命中", not_found is None)

        # ──── 测试 8: touch_last_used ────
        print("\n【测试 8】touch_last_used")
        before = updated.last_used_at
        await svc.touch_last_used(updated)
        after = (await svc.get(ak1_id, USER_A)).last_used_at
        report("last_used_at 已写入", after is not None)
        report("时间已更新", before != after)

        # ──── 测试 9: 鉴权依赖 - 缺失 header ────
        print("\n【测试 9】鉴权依赖各种边界")
        try:
            await get_user_by_api_key(raw_key=None, db=db)
            report("缺失 header 抛 401", False, "未抛异常")
        except HTTPException as e:
            report("缺失 header 抛 401", e.status_code == 401 and "X-API-Key" in e.detail)

        # 无效 key
        try:
            await get_user_by_api_key(raw_key="sk_nonexistent_key_xyz", db=db)
            report("无效 key 抛 401", False)
        except HTTPException as e:
            report("无效 key 抛 401", e.status_code == 401 and "无效" in e.detail)

        # 禁用
        await svc.update(ak1_id, USER_A, status_=0)
        try:
            await get_user_by_api_key(raw_key=ak1_raw, db=db)
            report("禁用 key 抛 401", False)
        except HTTPException as e:
            report("禁用 key 抛 401", e.status_code == 401 and "禁用" in e.detail)
        await svc.update(ak1_id, USER_A, status_=1)

        # 过期
        past = datetime.now() - timedelta(seconds=10)
        await svc.update(ak1_id, USER_A, expired_at=past)
        try:
            await get_user_by_api_key(raw_key=ak1_raw, db=db)
            report("过期 key 抛 401", False)
        except HTTPException as e:
            report("过期 key 抛 401", e.status_code == 401 and "过期" in e.detail)
        await svc.update(ak1_id, USER_A, expired_at=None)

        # 正常 key 通过
        try:
            user, ak = await get_user_by_api_key(raw_key=ak1_raw, db=db)
            report("有效 key 鉴权通过", user.id == USER_A and ak.id == ak1_id)
            # 此次调用应更新 last_used_at
            await db.refresh(ak)
            report("鉴权后 last_used_at 已更新", ak.last_used_at is not None)
        except HTTPException as e:
            report("有效 key 鉴权通过", False, str(e.detail))

        # ──── 测试 10: 未兑换券查询过滤 ────
        print("\n【测试 10】list_unexchanged_items 过滤逻辑")
        items, total = await svc.list_unexchanged_items(USER_A, page=1, page_size=50)
        codes = sorted(it.redemption_code for it in items)
        report("USER_A 命中 2 条", total == 2 and len(items) == 2)
        report("命中 CODE_USERA_001", "CODE_USERA_001" in codes)
        report("命中 CODE_USERA_002", "CODE_USERA_002" in codes)
        report("不含已兑换", "CODE_USERA_USED" not in codes)
        report("不含无码项", all(c is not None for c in codes))
        report("不含已过期", "CODE_USERA_EXP" not in codes)
        report("不含待支付订单项", "CODE_USERA_PEND" not in codes)
        report("不含已退款订单项", "CODE_USERA_RFND" not in codes)
        report("不含他人订单", "CODE_USERB_001" not in codes)

        # USER_B 隔离
        items_b, total_b = await svc.list_unexchanged_items(USER_B, page=1, page_size=50)
        report("USER_B 命中 1 条", total_b == 1)
        report("USER_B 兑换码正确", items_b and items_b[0].redemption_code == "CODE_USERB_001")

        # 关联对象已加载, 不会 lazy load
        for it in items:
            report(f"item {it.item_id} 关联 sku 已加载",
                   it.sku is not None and it.sku.sku_name == "TEST_SKU")
            report(f"item {it.item_id} 关联 order 已加载",
                   it.order is not None and it.order.order_no.startswith("TKO_"))

        # 分页
        items_p1, _ = await svc.list_unexchanged_items(USER_A, page=1, page_size=1)
        items_p2, _ = await svc.list_unexchanged_items(USER_A, page=2, page_size=1)
        report("分页 page=1 取 1 条", len(items_p1) == 1)
        report("分页 page=2 取 1 条", len(items_p2) == 1)
        report("分页 page=1/page=2 不重复",
               items_p1[0].item_id != items_p2[0].item_id)

        # ──── 测试 11: 全链路 - X-API-Key → 未兑换券 ────
        print("\n【测试 11】完整链路: 鉴权 → 查询")
        # 用 USER_B 的 raw_key 鉴权, 查到的应是 USER_B 的券
        user_b, ak_b_obj = await get_user_by_api_key(raw_key=raw_b, db=db)
        report("USER_B raw_key 鉴权返回正确 user", user_b.id == USER_B)
        items_via_b, total_via_b = await svc.list_unexchanged_items(user_b.id, 1, 50)
        report("通过 USER_B 的 key 只查到自己的券",
               total_via_b == 1 and items_via_b[0].redemption_code == "CODE_USERB_001")

        # ──── 测试 12: 哈希存储隐私 ────
        print("\n【测试 12】明文不入库")
        rows = (await db.execute(text(
            "SELECT key_hash, key_prefix FROM api_keys WHERE id=:i"
        ), {"i": ak1_id})).first()
        report("库内 key_hash 是哈希值",
               rows[0] == hashlib.sha256(ak1_raw.encode()).hexdigest())
        report("库内 key_prefix 不含完整明文",
               len(rows[1]) <= 16 and rows[1] != ak1_raw)

        # ──── 测试 12.5: dispatch_unexchanged_items 派发逻辑 ────
        print("\n【测试 12.5】dispatch_unexchanged_items 派发逻辑")

        order_no_paid = "TKO_9100"  # USER_A 已支付订单, 含 1 个可派发券 CODE_USERA_001
        order_no_done = "TKO_9101"  # USER_A 已完成订单, 含 1 个可派发券 CODE_USERA_002
        order_no_pend = "TKO_9102"  # USER_A 待支付订单, 不可派发
        order_no_rfnd = "TKO_9103"  # USER_A 已退款订单
        order_no_userb = "TKO_9104"  # USER_B 订单

        # 12.5.1 不存在的订单号 → 404
        try:
            await svc.dispatch_unexchanged_items(USER_A, "TKO_NOT_EXIST", 1)
            report("不存在订单号 抛 404", False)
        except HTTPException as e:
            report("不存在订单号 抛 404", e.status_code == 404)

        # 12.5.2 跨用户访问 → 404 (USER_A 访问 USER_B 的订单)
        try:
            await svc.dispatch_unexchanged_items(USER_A, order_no_userb, 1)
            report("跨用户订单号 抛 404", False)
        except HTTPException as e:
            report("跨用户订单号 抛 404", e.status_code == 404)

        # 12.5.3 待支付订单 → 400
        try:
            await svc.dispatch_unexchanged_items(USER_A, order_no_pend, 1)
            report("待支付订单 抛 400", False)
        except HTTPException as e:
            report("待支付订单 抛 400", e.status_code == 400)

        # 12.5.4 已退款订单(status=4 不在 [1,3]) → 400
        try:
            await svc.dispatch_unexchanged_items(USER_A, order_no_rfnd, 1)
            report("已退款订单 抛 400", False)
        except HTTPException as e:
            report("已退款订单 抛 400", e.status_code == 400)

        # 12.5.5 正常派发: TKO_9100 仅 1 个有效券, 请求 5 但只能拿到 1
        remain_before = await svc.count_remaining_undispatched_items(USER_A, order_no_paid)
        report("9100 派发前剩余未派发未兑换未退款未过期数量=2", remain_before == 2)
        items_d = await svc.dispatch_unexchanged_items(USER_A, order_no_paid, 5)
        remain_after = await svc.count_remaining_undispatched_items(USER_A, order_no_paid)
        report("9100 实际派发 1 张", len(items_d) == 1)
        report("9100 派发后剩余未派发未兑换未退款未过期数量=1", remain_after == 1)
        report("9100 兑换码正确", items_d and items_d[0].redemption_code == "CODE_USERA_001")
        report("9100 派发后写入 dispatched_at", items_d[0].dispatched_at is not None)
        report("9100 关联 sku 加载", items_d[0].sku is not None)
        report("9100 关联 order 加载", items_d[0].order is not None)

        # 12.5.6 二次派发同订单 → 已派发的不再返回, 0 张
        items_d2 = await svc.dispatch_unexchanged_items(USER_A, order_no_paid, 5)
        report("9100 二次派发返回空", items_d2 == [])

        # 12.5.7 已派发 item 不再出现在 list_unexchanged_items? 当前 list 仍按旧规则返回
        # (派发标记不影响旧的查询接口); 但应不影响其他订单
        items_d3 = await svc.dispatch_unexchanged_items(USER_A, order_no_done, 1)
        report("9101 派发 1 张", len(items_d3) == 1
               and items_d3[0].redemption_code == "CODE_USERA_002")

        # 12.5.8 dispatched_at 持久化校验: 直接查表
        row = (await db.execute(text(
            "SELECT dispatched_at FROM order_items WHERE redemption_code='CODE_USERA_001'"
        ))).first()
        report("CODE_USERA_001 dispatched_at 已落库", row[0] is not None)
        row2 = (await db.execute(text(
            "SELECT dispatched_at FROM order_items WHERE redemption_code='CODE_USERA_002'"
        ))).first()
        report("CODE_USERA_002 dispatched_at 已落库", row2[0] is not None)
        # 已退款订单的 item 不应被派发(尽管 9206 满足"未兑换+有码"也不应被取到)
        row3 = (await db.execute(text(
            "SELECT dispatched_at FROM order_items WHERE redemption_code='CODE_USERA_RFND'"
        ))).first()
        report("CODE_USERA_RFND 未被派发", row3[0] is None)

        # 12.5.9 dispatch_count<=0 由路由层 Query(gt=0) 拦截, service 层不强校验; 但 0 应返回空
        items_d_zero = await svc.dispatch_unexchanged_items(USER_A, order_no_paid, 0)
        report("dispatch_count=0 返回空", items_d_zero == [])

        # ──── 测试 12.6: query_coupon_status 状态查询 ────
        print("\n【测试 12.6】query_coupon_status 状态查询")

        # 12.6.1 不存在订单号 → 404
        try:
            await svc.query_coupon_status(USER_A, "TKO_NOT_EXIST")
            report("状态查询: 不存在订单号 抛 404", False)
        except HTTPException as e:
            report("状态查询: 不存在订单号 抛 404", e.status_code == 404)

        # 12.6.2 跨用户访问 → 404
        try:
            await svc.query_coupon_status(USER_A, order_no_userb)
            report("状态查询: 跨用户订单号 抛 404", False)
        except HTTPException as e:
            report("状态查询: 跨用户订单号 抛 404", e.status_code == 404)

        # 12.6.3 9100 含 4 个 item: 9200(已派发,未兑换), 9201(已兑换), 9202(无码,未兑换), 9203(已过期,未兑换)
        items_s = await svc.query_coupon_status(USER_A, order_no_paid)
        report("9100 状态查询返回 4 项", len(items_s) == 4)
        # 检查派发状态: 9200 之前已被派发; 其余未派发
        smap = {it.item_id: it for it in items_s}
        report("9200 dispatched_at 非空", smap[ITEM_BASE + 0].dispatched_at is not None)
        report("9201 dispatched_at 为空", smap[ITEM_BASE + 1].dispatched_at is None)
        report("9201 已兑换", smap[ITEM_BASE + 1].exchange_status == 1)
        report("9202 未兑换", smap[ITEM_BASE + 2].exchange_status == 0)
        report("9203 未兑换", smap[ITEM_BASE + 3].exchange_status == 0)

        # 12.6.4 已退款订单(status=4) 也支持查询(不限制订单状态)
        items_s2 = await svc.query_coupon_status(USER_A, order_no_rfnd)
        report("已退款订单可查询状态", len(items_s2) == 1)

        # 12.6.5 redemption_code 精确过滤
        items_s3 = await svc.query_coupon_status(USER_A, order_no_paid, redemption_code="CODE_USERA_001")
        report("按兑换码过滤 命中 1 项", len(items_s3) == 1
               and items_s3[0].redemption_code == "CODE_USERA_001")

        # 12.6.6 错误兑换码 → 空
        items_s4 = await svc.query_coupon_status(USER_A, order_no_paid, redemption_code="NO_SUCH_CODE")
        report("错误兑换码 返回空", items_s4 == [])

        # 12.6.7 关联对象已加载
        report("9200 关联 sku 加载", smap[ITEM_BASE + 0].sku is not None)
        report("9200 关联 order 加载", smap[ITEM_BASE + 0].order is not None)

        # ──── 测试 12.7: list_external_orders 外部订单查询 ────
        print("\n【测试 12.7】list_external_orders 外部订单查询")
        orders_a = await svc.list_external_orders(USER_A)
        orders_b = await svc.list_external_orders(USER_B)
        order_nos_a = {order.order_no for order, _ in orders_a}
        order_nos_b = {order.order_no for order, _ in orders_b}
        report("USER_A 至少返回本测试的 4 个订单", len(orders_a) >= 4)
        report("USER_A 包含 TKO_9100", "TKO_9100" in order_nos_a)
        report("USER_A 包含 TKO_9101", "TKO_9101" in order_nos_a)
        report("USER_A 包含 TKO_9102", "TKO_9102" in order_nos_a)
        report("USER_A 包含 TKO_9103", "TKO_9103" in order_nos_a)
        report("USER_A 不含 USER_B 订单", "TKO_9104" not in order_nos_a)
        report("USER_B 返回 1 个订单", len(orders_b) == 1 and "TKO_9104" in order_nos_b)
        a_map = {order.order_no: (order, expired_at) for order, expired_at in orders_a}
        report("订单查询返回订单号", a_map["TKO_9100"][0].order_no == "TKO_9100")
        report("订单查询返回创建时间", a_map["TKO_9100"][0].created_at is not None)
        report("订单查询返回订单总金额", a_map["TKO_9100"][0].total_amount == Decimal("100.00"))
        report("订单查询返回订单状态", a_map["TKO_9100"][0].status == 1)
        report("订单查询返回已退款金额", a_map["TKO_9100"][0].refunded_amount == Decimal("0.00"))
        report("订单查询返回最早过期时间", a_map["TKO_9100"][1] is not None)
        report("订单查询已退款订单状态正确", a_map["TKO_9103"][0].status == 4)

        # ──── 测试 13: delete ────
        print("\n【测试 13】delete")
        # 他人删不了
        ok = await svc.delete(ak1_id, USER_B)
        report("他人 delete 返回 False", ok is False)
        ok = await svc.delete(ak1_id, USER_A)
        report("本人 delete 返回 True", ok is True)
        # 删后查不到
        gone = await svc.get(ak1_id, USER_A)
        report("删除后 get 返回 None", gone is None)
        # 删后 raw_key 鉴权 401
        try:
            await get_user_by_api_key(raw_key=ak1_raw, db=db)
            report("删除后 raw_key 失效", False)
        except HTTPException as e:
            report("删除后 raw_key 失效", e.status_code == 401)
        # 不存在 id 删除返回 False
        ok = await svc.delete(99999999, USER_A)
        report("删除不存在 id 返回 False", ok is False)

        # ──── 清理 ────
        await cleanup_data(db)

    print(f"\n{'='*50}")
    print(f"  通过: {passed}  失败: {failed}  总计: {passed + failed}")
    if failed == 0:
        print("  🎉 全部测试通过!")
    else:
        print("  ⚠️  有测试失败, 请检查上方详情")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(run_tests())
