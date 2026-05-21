from datetime import datetime

from pydantic import BaseModel, Field


class CreatePaymentRequest(BaseModel):
    """发起支付请求参数"""

    model_config = {"title": "创建支付请求"}

    order_id: int = Field(..., gt=0, title="订单ID", description="订单ID，必须大于0")


class PaymentResponse(BaseModel):
    """创建支付后返回的扫码支付信息"""

    model_config = {"title": "支付响应"}

    order_no: str = Field(title="订单编号", description="订单编号")
    code_url: str = Field(title="微信扫码支付链接", description="微信扫码支付链接")


class PaymentStatusResponse(BaseModel):
    """订单支付状态查询结果"""

    model_config = {"title": "支付状态响应", "from_attributes": True}

    order_id: int = Field(title="订单ID", description="订单ID")
    order_no: str = Field(title="订单编号", description="订单编号")
    status: int = Field(title="订单状态", description="订单状态，0-待支付 1-已支付 2-已取消 3-已完成")
    status_text: str = Field(title="状态文本", description="状态文本描述")
    paid_at: datetime | None = Field(default=None, title="支付时间", description="支付完成时间")


class PaymentNotifyResponse(BaseModel):
    """微信支付回调处理结果"""

    model_config = {"title": "支付回调响应"}

    code: str = Field(title="处理结果", description="处理结果，SUCCESS-成功")
    message: str = Field(title="结果信息", description="结果信息")
