from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class CreateRefundRequest(BaseModel):
    """管理员发起退款请求参数"""

    model_config = {"title": "创建退款请求"}

    order_id: int = Field(..., gt=0, title="订单ID", description="要退款的订单ID")
    refund_type: str = Field(default="partial", title="退款类型", description="退款类型: full=全额退款(仅退未兑换项, 退款金额=未兑换项对应 sku 面值之和), partial=部分退款(手动指定金额和项)")
    refund_amount: Decimal | None = Field(default=None, gt=0, decimal_places=2, title="退款金额", description="本次退款金额(元)；全额退款时无需传入(自动按未兑换项 sku 面值之和计算)")
    reason: str | None = Field(default=None, max_length=255, title="退款原因", description="退款原因说明")
    item_ids: list[int] | None = Field(default=None, title="订单项ID列表", description="本次退款关联的订单项ID列表；全额退款时无需传入(自动收集全部未兑换项)")

    @model_validator(mode="after")
    def _validate_refund_type(self):
        if self.refund_type not in ("full", "partial"):
            raise ValueError("refund_type must be 'full' or 'partial'")
        if self.refund_type == "partial" and self.refund_amount is None:
            raise ValueError("refund_amount is required for partial refund")
        return self


class RefundCreateResponse(BaseModel):
    """创建退款响应"""

    model_config = {"title": "退款创建响应"}

    refund_id: int = Field(title="退款记录ID", description="退款记录ID")
    refund_no: str = Field(title="退款单号", description="商户退款单号")
    refund_amount: Decimal = Field(title="退款金额", description="本次退款金额(元)")
    status: int = Field(title="退款状态", description="退款状态: 0=处理中, 1=成功, 2=失败, 3=异常")
    status_text: str = Field(title="状态文本", description="状态中文描述")


class RefundInfo(BaseModel):
    """退款详情"""

    model_config = {"title": "退款详情", "from_attributes": True}

    refund_id: int = Field(title="退款记录ID", description="退款记录ID")
    refund_no: str = Field(title="退款单号", description="商户退款单号")
    order_id: int = Field(title="订单ID", description="关联订单ID")
    order_no: str = Field(title="订单号", description="关联订单号")
    refund_amount: Decimal = Field(title="退款金额", description="本次退款金额(元)")
    total_amount: Decimal = Field(title="订单总额", description="订单原总额(元)")
    reason: str | None = Field(default=None, title="退款原因", description="退款原因")
    status: int = Field(title="退款状态", description="退款状态: 0=处理中, 1=成功, 2=失败, 3=异常")
    wechat_refund_id: str | None = Field(default=None, title="微信退款单号", description="微信退款单号")
    transaction_id: str | None = Field(default=None, title="原支付交易号", description="原支付交易号")
    operator_id: int = Field(title="操作管理员ID", description="发起退款的管理员ID")
    channel: int = Field(title="退款渠道", description="退款渠道: 1=微信")
    error_msg: str | None = Field(default=None, title="异常信息", description="失败或异常的详细信息")
    item_ids: str | None = Field(default=None, title="订单项ID列表", description="本次退款关联的订单项ID(JSON字符串)")
    disable_result: str | None = Field(default=None, title="兑换码作废结果", description="兑换码作废结果(JSON字符串)")
    created_at: datetime = Field(title="创建时间", description="创建时间")
    updated_at: datetime = Field(title="更新时间", description="更新时间")


class RefundListQuery(BaseModel):
    """退款列表查询参数"""

    model_config = {"title": "退款列表查询参数"}

    order_no: str | None = Field(default=None, title="订单号", description="按订单号筛选")
    refund_no: str | None = Field(default=None, title="退款单号", description="按退款单号筛选")
    status: int | None = Field(default=None, title="退款状态", description="按退款状态筛选")
    page: int = Field(default=1, ge=1, title="页码", description="页码")
    page_size: int = Field(default=20, ge=1, le=100, title="每页条数", description="每页条数")


class RefundListResponse(BaseModel):
    """退款分页列表"""

    model_config = {"title": "退款列表响应"}

    items: list[RefundInfo] = Field(title="退款列表", description="退款列表")
    total: int = Field(title="总数", description="总数")
    page: int = Field(title="当前页码", description="当前页码")
    page_size: int = Field(title="每页数量", description="每页数量")