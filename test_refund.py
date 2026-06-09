"""
微信退款功能完整测试脚本
- Mock 微信 API，测试本地业务逻辑全链路
- 覆盖: 权限控制、参数校验、全额退款、部分退款、回调处理、幂等性、列表查询
"""
import asyncio
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from app.core.database import async_session
from app.core.security import create_access_token
from app.models.order import Order
from app.models.refund import Refund
from app.services.refund_service import REFUND_STATUS_TEXT, RefundService
from app.services.wechat_pay_service import WechatPayService

from sqlalchemy import select, text


# ── helpers ──

class MockPayService:
    """模拟微信支付服务，不调用真实 API"""
    def __init__(self, refund_status="SUCCESS"):
        self._refund_status = refund_status
        self._refund_id = "5030000120202606090000000001"
        self.create_refund = AsyncMock(return_value={
            "refund_id": self._refund_id,
            "out_refund_no": "",
            "out_trade_no": "",
            "status": self._refund_status,
            "channel": "ORIGINAL",
            "create_time": "2026-06-09T16:00:00+08:00",
        })
        self.query_refund = AsyncMock(return_value={
            "refund_id": self._refund_id,
            "out_refund_no": "",
            "status": self._refund_status,
            "channel": "ORIGINAL",
        })


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


async def run_tests():
    async with async_session() as db:
        svc = RefundService(db)

        # ──── 准备数据 ────
        await db.execute(text("DELETE FROM refunds"))
        # 重置订单状态
        await db.execute(text("UPDATE orders SET refunded_amount=0, status=1 WHERE order_id=49"))
        await db.execute(text("UPDATE orders SET refunded_amount=0, status=3 WHERE order_id=50"))
        await db.execute(text("UPDATE orders SET status=0 WHERE order_id=51"))
        await db.execute(text("UPDATE orders SET status=2 WHERE order_id=52"))
        await db.commit()
        print("\n=== 数据准备完成 ===")

        # ──── 测试 1: 已支付订单全额退款 (微信返回 SUCCESS) ────
        print("\n【测试 1】已支付订单全额退款 — 微信同步返回 SUCCESS")
        pay_svc = MockPayService("SUCCESS")
        refund = await svc.create_refund(
            order_id=49, refund_amount=Decimal("100.00"),
            reason="测试全额退款", operator_id=1, pay_svc=pay_svc,
        )
        report("退款记录创建", refund is not None)
        report("refund_no 格式", refund.refund_no.startswith("R"))
        report("退款金额", refund.refund_amount == Decimal("100.00"))
        report("退款状态=1(成功)", refund.status == 1)
        report("微信退款单号已记录", refund.wechat_refund_id == pay_svc._refund_id)

        # 检查订单状态
        order = (await db.execute(select(Order).where(Order.order_id == 49))).scalar_one()
        report("订单 status=4(已退款)", order.status == 4)
        report("订单 refunded_amount=100", order.refunded_amount == Decimal("100.00"))

        # ──── 测试 2: 已完成订单部分退款 (微信返回 PROCESSING) ────
        print("\n【测试 2】已完成订单部分退款 — 微信返回 PROCESSING")
        pay_svc2 = MockPayService("PROCESSING")
        refund2 = await svc.create_refund(
            order_id=50, refund_amount=Decimal("50.00"),
            reason="部分退款", operator_id=1, pay_svc=pay_svc2,
        )
        report("退款记录创建", refund2 is not None)
        report("退款金额=50", refund2.refund_amount == Decimal("50.00"))
        report("退款状态=0(处理中)", refund2.status == 0)
        report("微信退款单号已记录", refund2.wechat_refund_id == pay_svc2._refund_id)

        # 订单此时还不应该是已退款(因为 PROCESSING)
        order2 = (await db.execute(select(Order).where(Order.order_id == 50))).scalar_one()
        report("订单 status 仍=3", order2.status == 3)
        report("订单 refunded_amount=0", order2.refunded_amount == Decimal("0"))

        # ──── 测试 3: 模拟退款回调 — PROCESSING 的退款收到 SUCCESS 回调
        print("\n【测试 3】退款回调 — PROCESSING → SUCCESS")
        result = await svc.apply_refund_success(
            refund_no=refund2.refund_no,
            wechat_refund_id="5030000120202606090000000999",
            notify_payload='{"refund_status":"SUCCESS"}',
        )
        report("回调处理成功", result is not None)
        report("退款状态=1", result.status == 1)
        report("微信退款单号更新", result.wechat_refund_id == "5030000120202606090000000999")

        order2 = (await db.execute(select(Order).where(Order.order_id == 50))).scalar_one()
        report("订单 status=4(已退款)", order2.status == 4)
        report("订单 refunded_amount=50", order2.refunded_amount == Decimal("50.00"))

        # ──── 测试 4: 回调幂等性 — 重复回调不应重复累加金额
        print("\n【测试 4】回调幂等性 — 重复推送同一退款单号")
        result2 = await svc.apply_refund_success(
            refund_no=refund2.refund_no,
            wechat_refund_id="5030000120202606090000000999",
            notify_payload='{"refund_status":"SUCCESS"}',
        )
        report("幂等返回成功", result2 is not None)
        order2 = (await db.execute(select(Order).where(Order.order_id == 50))).scalar_one()
        report("金额未重复累加(仍=50)", order2.refunded_amount == Decimal("50.00"))

        # ──── 测试 5: 部分退款 — 对已部分退款的订单再退剩余金额
        print("\n【测试 5】二次部分退款 — 退剩余金额")
        pay_svc5 = MockPayService("SUCCESS")
        refund5 = await svc.create_refund(
            order_id=50, refund_amount=Decimal("150.00"),
            reason="退剩余", operator_id=1, pay_svc=pay_svc5,
        )
        report("退款记录创建", refund5 is not None)
        report("退款金额=150", refund5.refund_amount == Decimal("150.00"))
        report("退款状态=1(成功)", refund5.status == 1)

        order2 = (await db.execute(select(Order).where(Order.order_id == 50))).scalar_one()
        report("累计退款=200", order2.refunded_amount == Decimal("200.00"))

        # ──── 测试 6: 退款金额超额校验
        print("\n【测试 6】退款金额超额校验")
        try:
            pay_svc6 = MockPayService("SUCCESS")
            await svc.create_refund(
                order_id=49, refund_amount=Decimal("1.00"),
                reason="超额测试", operator_id=1, pay_svc=pay_svc6,
            )
            report("超额退款被拒绝", False, "未抛异常")
        except HTTPException as e:
            report("超额退款被拒绝", "exceeds remaining" in e.detail or "超出" in e.detail, f"detail={e.detail}")

        # ──── 测试 7: 待支付订单不可退款
        print("\n【测试 7】待支付订单不可退款")
        try:
            pay_svc7 = MockPayService("SUCCESS")
            await svc.create_refund(
                order_id=51, refund_amount=Decimal("50.00"),
                reason="待支付测试", operator_id=1, pay_svc=pay_svc7,
            )
            report("待支付订单被拒绝", False, "未抛异常")
        except HTTPException as e:
            report("待支付订单被拒绝", e.status_code == 400, f"detail={e.detail}")

        # ──── 测试 8: 已取消订单不可退款
        print("\n【测试 8】已取消订单不可退款")
        try:
            pay_svc8 = MockPayService("SUCCESS")
            await svc.create_refund(
                order_id=52, refund_amount=Decimal("80.00"),
                reason="已取消测试", operator_id=1, pay_svc=pay_svc8,
            )
            report("已取消订单被拒绝", False, "未抛异常")
        except HTTPException as e:
            report("已取消订单被拒绝", e.status_code == 400, f"detail={e.detail}")

        # ──── 测试 9: 不存在的订单
        print("\n【测试 9】不存在的订单")
        try:
            pay_svc9 = MockPayService("SUCCESS")
            await svc.create_refund(
                order_id=9999, refund_amount=Decimal("10.00"),
                reason="不存在测试", operator_id=1, pay_svc=pay_svc9,
            )
            report("不存在订单返回404", False, "未抛异常")
        except HTTPException as e:
            report("不存在订单返回404", e.status_code == 404, f"detail={e.detail}")

        # ──── 测试 10: 退款回调 — 失败分支
        print("\n【测试 10】退款回调 — 失败分支")
        # 重置订单 49 状态（测试 1 全额退款后需要重置）
        await db.execute(text("UPDATE orders SET refunded_amount=0, status=1 WHERE order_id=49"))
        await db.commit()
        db.expire_all()  # 清除 ORM 缓存
        pay_svc10 = MockPayService("PROCESSING")
        refund10 = await svc.create_refund(
            order_id=49, refund_amount=Decimal("30.00"),
            reason="回调失败测试", operator_id=1, pay_svc=pay_svc10,
        )
        # 模拟回调通知退款失败
        result10 = await svc.apply_refund_failure(
            refund_no=refund10.refund_no,
            error_msg="WeChat refund_status=CLOSED",
            notify_payload='{"refund_status":"CLOSED"}',
        )
        report("失败回调处理成功", result10 is not None)
        report("退款状态=2(失败)", result10.status == 2)
        report("error_msg 已记录", "CLOSED" in (result10.error_msg or ""))

        order10 = (await db.execute(select(Order).where(Order.order_id == 49))).scalar_one()
        report("订单状态未变(不=4)", order10.status != 4)
        report("订单 refunded_amount=0", order10.refunded_amount == Decimal("0"))

        # ──── 测试 11: 退款列表查询
        print("\n【测试 11】退款列表查询")
        items, total = await svc.list_refunds(order_no=None, refund_no=None, status_=None, page=1, page_size=10)
        report("退款列表有数据", total > 0)
        report(f"总数={total}", total >= 3, f"实际={total}")

        # 按状态筛选
        items_ok, total_ok = await svc.list_refunds(order_no=None, refund_no=None, status_=1, page=1, page_size=10)
        report("筛选成功退款", total_ok >= 2, f"成功数={total_ok}")

        # ──── 测试 12: 退款详情
        print("\n【测试 12】退款详情")
        detail = await svc.get_refund_detail(refund.refund_id)
        report("退款详情查询成功", detail is not None)
        report("详情 refund_no 匹配", detail.refund_no == refund.refund_no)

        # ──── 测试 13: 主动同步退款状态(从微信查询) — 兜底接口
        print("\n【测试 13】主动同步退款状态 — 兜底接口")
        # refund10 已失败(status=2), sync 应直接返回不再调微信 — 测试幂等跳过
        pay_svc13a = MockPayService("SUCCESS")
        sync_result_a = await svc.sync_refund_from_wechat(refund10.refund_id, pay_svc13a)
        report("已失败退款 sync 直接返回", sync_result_a is not None)
        report("已失败退款 sync 状态不变(仍=2)", sync_result_a.status == 2)

        # 对状态=0(处理中)的退款做同步 — 使用退款 2(refund2, 仍为 PROCESSING)
        # 先把它重置为 status=0 以便测试 sync
        refund2_id = refund2.refund_id
        refund2_no = refund2.refund_no
        await db.execute(text(f"UPDATE refunds SET status=0 WHERE refund_no='{refund2_no}'"))
        await db.commit()
        db.expire_all()
        pay_svc13b = MockPayService("SUCCESS")
        sync_result_b = await svc.sync_refund_from_wechat(refund2_id, pay_svc13b)
        report("处理中退款 sync 成功", sync_result_b is not None)
        report("sync 后状态=1(成功)", sync_result_b.status == 1, f"实际={sync_result_b.status}")

        # ──── 测试 14: 微信返回 ABNORMAL 状态
        print("\n【测试 14】微信返回 ABNORMAL 状态")
        await db.execute(text("UPDATE orders SET refunded_amount=0, status=1 WHERE order_id=49"))
        await db.commit()
        db.expire_all()
        pay_svc14 = MockPayService("ABNORMAL")
        refund14 = await svc.create_refund(
            order_id=49, refund_amount=Decimal("10.00"),
            reason="异常测试", operator_id=1, pay_svc=pay_svc14,
        )
        report("退款记录创建", refund14 is not None)
        report("退款状态=3(异常)", refund14.status == 3, f"实际={refund14.status}")
        report("error_msg 有内容", bool(refund14.error_msg))

        # ──── 测试 15: API 权限验证 — 通过 HTTP 请求测试
        print("\n【测试 15】API 权限验证")
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        from app.core.redis import init_redis, close_redis

        # 保存 ID 避免后续 session 状态问题
        saved_refund_id = refund.refund_id

        await init_redis()
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 15a. 无 token
                resp = await client.post("/api/refund/create", json={"order_id": 49, "refund_amount": "10.00"})
                report("无token返回401", resp.status_code == 401, f"实际={resp.status_code}")

                # 15b. 普通用户
                user_token = create_access_token({"sub": "13", "username": "grey_test", "role": 1})
                resp = await client.post(
                    "/api/refund/create",
                    json={"order_id": 49, "refund_amount": "10.00"},
                    headers={"Authorization": f"Bearer {user_token}"},
                )
                report("普通用户返回403", resp.status_code == 403, f"实际={resp.status_code}")

                # 15c. 管理员访问列表
                admin_token = create_access_token({"sub": "1", "username": "admin", "role": 10})
                resp = await client.get(
                    "/api/refund/admin/list",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                report("管理员退款列表200", resp.status_code == 200, f"实际={resp.status_code}")
                data = resp.json()
                report("列表返回 total>0", data["total"] > 0, f"total={data['total']}")

                # 15d. 管理员退款详情
                resp = await client.get(
                    f"/api/refund/admin/{saved_refund_id}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                report("管理员退款详情200", resp.status_code == 200, f"实际={resp.status_code}")

                # 15e. 退款回调接口 — 无效签名应静默返回 SUCCESS
                resp = await client.post(
                    "/api/refund/notify",
                    content=b'{"test":1}',
                    headers={
                        "Wechatpay-Signature": "fake",
                        "Wechatpay-Timestamp": "0",
                        "Wechatpay-Nonce": "fake",
                        "Wechatpay-Serial": "fake",
                    },
                )
                report("无效签名回调返回200", resp.status_code == 200, f"实际={resp.status_code}")
                report("回调返回 SUCCESS", resp.json().get("code") == "SUCCESS")
        finally:
            await close_redis()

    # ──── 汇总 ────
    print(f"\n{'='*50}")
    print(f"  通过: {passed}  失败: {failed}  总计: {passed + failed}")
    if failed == 0:
        print("  🎉 全部测试通过!")
    else:
        print("  ⚠️  有测试失败，请检查上方详情")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(run_tests())
