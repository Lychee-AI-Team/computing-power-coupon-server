from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.schemas.sku import SkuItem


class OrderItemInfo(BaseModel):
    """订单中单个SKU项的详细信息"""

    model_config = {"title": "订单项信息", "from_attributes": True}

    item_id: int = Field(title="订单项ID", description="订单项ID")
    order_id: int = Field(title="订单ID", description="订单ID")
    sku_id: int = Field(title="SKU ID", description="SKU ID")
    exchange_status: int = Field(title="兑换状态", description="兑换状态")
    exchange_user_id: int | None = Field(title="兑换用户ID", description="兑换用户ID")
    expired_at: datetime | None = Field(title="过期时间", description="过期时间")
    redemption_code: str | None = Field(default=None, title="兑换码", description="兑换码")
    redemption_status: int = Field(default=0, title="兑换码状态", description="兑换码生成状态: 0=待生成, 1=生成中, 2=已生成, 3=生成失败")
    created_at: datetime = Field(title="创建时间", description="创建时间")
    updated_at: datetime = Field(title="更新时间", description="更新时间")
    sku: SkuItem | None = Field(default=None, title="SKU详情", description="对应SKU的完整信息")


class OrderInfo(BaseModel):
    """订单详细信息"""

    model_config = {"title": "订单信息", "from_attributes": True}

    order_id: int = Field(title="订单ID", description="订单ID")
    order_no: str = Field(title="订单编号", description="订单编号")
    user_id: int = Field(title="用户ID", description="用户ID")
    username: str | None = Field(default=None, title="用户名", description="用户名")
    display_name: str | None = Field(default=None, title="显示名称", description="显示名称")
    total_amount: Decimal = Field(title="订单总金额", description="订单总金额")
    status: int = Field(title="订单状态", description="订单状态，0-待支付 1-已支付 2-已取消 3-已完成")
    pay_channel: int | None = Field(default=None, title="支付渠道", description="支付渠道")
    transaction_id: str | None = Field(default=None, title="第三方交易号", description="第三方交易号")
    pay_info: str | None = Field(default=None, title="支付信息", description="支付信息")
    created_at: datetime = Field(title="创建时间", description="创建时间")
    updated_at: datetime = Field(title="更新时间", description="更新时间")
    items: list[OrderItemInfo] = Field(default=[], title="订单项列表", description="订单项列表")

    @model_validator(mode="before")
    @classmethod
    def _extract_user_info(cls, data):
        if isinstance(data, dict):
            user = data.get("user")
            if user is not None:
                data.setdefault("username", getattr(user, "username", None))
                data.setdefault("display_name", getattr(user, "display_name", None))
            return data
        user = getattr(data, "user", None)
        if user is not None:
            try:
                if not getattr(data, "username", None):
                    setattr(data, "username", getattr(user, "username", None))
                if not getattr(data, "display_name", None):
                    setattr(data, "display_name", getattr(user, "display_name", None))
            except Exception:
                pass
        return data


class OrderListResponse(BaseModel):
    """订单分页列表"""

    model_config = {"title": "订单列表响应"}

    items: list[OrderInfo] = Field(title="订单列表", description="订单列表")
    total: int = Field(title="总数", description="总数")
    page: int = Field(title="当前页码", description="当前页码")
    page_size: int = Field(title="每页数量", description="每页数量")


class CreateOrderRequest(BaseModel):
    """从购物车创建订单请求参数"""

    model_config = {"title": "创建订单请求"}

    cart_item_ids: list[int] = Field(..., min_length=1, title="购物车项ID列表", description="要下单的购物车项ID列表，至少包含一项")


class OrderQueryParams(BaseModel):
    """用户端订单查询筛选参数"""

    model_config = {"title": "订单查询参数"}

    status: int | None = Field(default=None, title="订单状态", description="订单状态")
    order_no: str | None = Field(default=None, title="订单编号", description="订单编号")


class AdminOrderQueryParams(BaseModel):
    """管理员端订单查询筛选参数"""

    model_config = {"title": "管理员订单查询参数"}

    user_id: int | None = Field(default=None, title="用户ID", description="用户ID")
    status: int | None = Field(default=None, title="订单状态", description="订单状态")
    order_no: str | None = Field(default=None, title="订单编号", description="订单编号")
