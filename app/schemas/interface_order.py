from pydantic import BaseModel, Field

# 订单级聚合生成状态
ORDER_STATUS_GENERATING = "generating"
ORDER_STATUS_FAILED = "failed"
ORDER_STATUS_SUCCESS = "success"
ORDER_STATUS_TEXT = {
    ORDER_STATUS_GENERATING: "生成中",
    ORDER_STATUS_FAILED: "生成失败",
    ORDER_STATUS_SUCCESS: "生成成功",
}


class InterfaceOrderRequest(BaseModel):
    """接口下单请求"""

    model_config = {"title": "接口下单请求"}

    user_id: int = Field(..., gt=0, title="用户ID", description="必须与 X-API-Key 所属用户一致，且在白名单内")
    sku_id: int = Field(..., gt=0, title="SKU ID")
    quantity: int = Field(..., gt=0, le=100, title="数量")
    client_order_no: str = Field(..., min_length=1, max_length=64, title="客户侧订单号")


class InterfaceOrderCreateResponse(BaseModel):
    """接口下单响应: 立即返回平台订单号, 兑换码后台异步生成"""

    model_config = {"title": "接口下单响应"}

    success: bool = Field(title="调用状态")
    message: str = Field(title="结果描述")
    order_no: str | None = Field(default=None, title="平台订单号", description="用于后续查询卡密与生成状态")
    client_order_no: str | None = Field(default=None, title="客户侧订单号")


class InterfaceOrderStatusResponse(BaseModel):
    """接口订单查询响应"""

    model_config = {"title": "接口订单查询响应"}

    success: bool = Field(title="调用状态")
    message: str = Field(title="结果描述")
    order_no: str = Field(title="平台订单号")
    order_status: str = Field(title="订单生成状态", description="generating=生成中, failed=生成失败, success=生成成功")
    order_status_text: str = Field(title="订单生成状态描述")
    total: int = Field(title="卡密应生成总数", description="订单项总数, 即卡密总数")
    codes: list[str] = Field(default=[], title="卡密数组", description="仅 order_status=success 时返回全部卡密, 其他状态为空数组")

