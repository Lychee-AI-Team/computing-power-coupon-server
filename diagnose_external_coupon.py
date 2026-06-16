"""
诊断: 为什么 /api/external/coupons/unexchanged 返回空?
逐级放宽过滤条件, 找出是哪一步把数据过滤掉的.

使用: python3 diagnose_external_coupon.py <raw_api_key>
默认使用 sk_3bc7552ba2b129cc362ec7e128573e10
"""
import asyncio
import hashlib
import logging
import sys

logging.disable(logging.CRITICAL)

from app.core.database import async_session, engine
from sqlalchemy import text


async def main(raw_key: str):
    print(f"DB engine: {engine.url}")
    print(f"raw_key: {raw_key}")
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    print(f"sha256: {key_hash}\n")

    async with async_session() as db:
        ak = (await db.execute(text("""
            SELECT id, user_id, name, status, expired_at, last_used_at
            FROM api_keys WHERE key_hash=:h
        """), {"h": key_hash})).first()
        if not ak:
            print("❌ 该 raw_key 在当前 DB 中不存在 — 鉴权应当 401")
            return
        print(f"✅ 命中 api_key id={ak[0]} user_id={ak[1]} name={ak[2]} status={ak[3]} "
              f"expired_at={ak[4]} last_used_at={ak[5]}")
        user_id = ak[1]

        # 鉴权层会拦截
        if ak[3] != 1:
            print(f"❌ status != 1 (实际={ak[3]}) — 鉴权应当 401 '已禁用'")
        if ak[4] is not None:
            from datetime import datetime
            if ak[4] <= datetime.now():
                print(f"❌ expired_at 已过期 ({ak[4]}) — 鉴权应当 401 '已过期'")

        # 用户存在性
        u = (await db.execute(text("SELECT id, username FROM users WHERE id=:u"),
                              {"u": user_id})).first()
        print(f"\nuser_id={user_id} 用户记录: {u}")

        # 逐级过滤诊断
        print(f"\n=== 逐级过滤诊断 (user_id={user_id}) ===")
        steps = [
            ("user 名下 orders 总数",
             "SELECT COUNT(*) FROM orders WHERE user_id=:u"),
            ("orders 按 status 分布",
             "SELECT status, COUNT(*) FROM orders WHERE user_id=:u GROUP BY status"),
            ("user 名下 order_items 总数",
             """SELECT COUNT(*) FROM order_items oi
                JOIN orders o ON oi.order_id=o.order_id
                WHERE o.user_id=:u"""),
            ("  + exchange_status=0 (未兑换)",
             """SELECT COUNT(*) FROM order_items oi
                JOIN orders o ON oi.order_id=o.order_id
                WHERE o.user_id=:u AND oi.exchange_status=0"""),
            ("  + redemption_code IS NOT NULL",
             """SELECT COUNT(*) FROM order_items oi
                JOIN orders o ON oi.order_id=o.order_id
                WHERE o.user_id=:u AND oi.exchange_status=0
                AND oi.redemption_code IS NOT NULL"""),
            ("  + Order.status IN (1,3) (已支付/已完成)",
             """SELECT COUNT(*) FROM order_items oi
                JOIN orders o ON oi.order_id=o.order_id
                WHERE o.user_id=:u AND oi.exchange_status=0
                AND oi.redemption_code IS NOT NULL
                AND o.status IN (1,3)"""),
            ("  + 未过期 (最终结果)",
             """SELECT COUNT(*) FROM order_items oi
                JOIN orders o ON oi.order_id=o.order_id
                WHERE o.user_id=:u AND oi.exchange_status=0
                AND oi.redemption_code IS NOT NULL
                AND o.status IN (1,3)
                AND (oi.expired_at IS NULL OR oi.expired_at > NOW())"""),
        ]
        for label, sql in steps:
            rows = (await db.execute(text(sql), {"u": user_id})).all()
            if len(rows) == 1 and len(rows[0]) == 1:
                print(f"  {label}: {rows[0][0]}")
            else:
                print(f"  {label}:")
                for r in rows:
                    print(f"    {r}")

        # 把每个被过滤掉的 item 列出来, 标注被哪一步淘汰
        print(f"\n=== 用户名下所有 order_items 详情 (最多 30 条) ===")
        rows = (await db.execute(text("""
            SELECT oi.item_id, oi.order_id, o.status AS order_status,
                   oi.exchange_status, oi.redemption_status,
                   (oi.redemption_code IS NULL) AS no_code,
                   oi.expired_at,
                   (oi.expired_at IS NOT NULL AND oi.expired_at <= NOW()) AS expired
            FROM order_items oi
            JOIN orders o ON oi.order_id=o.order_id
            WHERE o.user_id=:u
            ORDER BY oi.item_id DESC
            LIMIT 30
        """), {"u": user_id})).all()
        if not rows:
            print("  (无任何 order_items)")
        else:
            print(f"  {'item_id':>8} {'order_id':>8} {'o.status':>8} {'ex_st':>5} {'rd_st':>5} "
                  f"{'no_code':>7} {'expired':>7}  reason")
            for r in rows:
                reasons = []
                if r[2] not in (1, 3):
                    reasons.append(f"order.status={r[2]}∉(1,3)")
                if r[3] != 0:
                    reasons.append(f"exchange_status={r[3]}")
                if r[5]:
                    reasons.append("redemption_code=NULL")
                if r[7]:
                    reasons.append("已过期")
                tag = "✅ 命中" if not reasons else "❌ " + " & ".join(reasons)
                print(f"  {r[0]:>8} {r[1]:>8} {r[2]:>8} {r[3]:>5} {r[4]:>5} "
                      f"{int(bool(r[5])):>7} {int(bool(r[7])):>7}  {tag}")


if __name__ == "__main__":
    raw_key = sys.argv[1] if len(sys.argv) > 1 else "sk_3bc7552ba2b129cc362ec7e128573e10"
    asyncio.run(main(raw_key))
