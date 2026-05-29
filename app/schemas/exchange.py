from pydantic import BaseModel, Field


class ExternalRedeemRequest(BaseModel):
    """外部平台兑换请求"""

    model_config = {"title": "外部兑换请求"}

    redemption_code: str = Field(..., min_length=1, max_length=128, title="兑换码", description="订单项兑换码")
    external_user_id: int = Field(..., gt=0, title="外部平台用户ID", description="外部平台用户ID，用于匹配本地用户")


class ExternalRedeemData(BaseModel):
    """外部平台兑换结果数据"""

    model_config = {"title": "外部兑换结果", "from_attributes": True}

    item_id: int = Field(title="订单项ID")
    order_id: int = Field(title="订单ID")
    exchange_status: int = Field(title="兑换状态")
    exchange_user_id: int | None = Field(title="兑换用户ID")
    redemption_code: str | None = Field(title="兑换码")


class ExternalRedeemResponse(BaseModel):
    """外部平台兑换响应"""

    model_config = {"title": "外部兑换响应"}

    success: bool = Field(title="是否成功")
    message: str = Field(title="结果描述")
    data: ExternalRedeemData | None = Field(default=None, title="兑换结果数据")
