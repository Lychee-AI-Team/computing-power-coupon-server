from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class CartAddRequest(BaseModel):
    """添加SKU到购物车请求参数"""

    model_config = {"title": "添加购物车请求"}

    sku_id: int = Field(..., gt=0, title="SKU ID", description="SKU ID，必须大于0")
    quantity: int = Field(default=1, ge=1, title="数量", description="添加数量，默认1")


class CartItemInfo(BaseModel):
    """购物车项详细信息（含SKU信息）"""

    model_config = {"title": "购物车项信息", "from_attributes": True}

    id: int = Field(title="购物车项ID", description="购物车项ID")
    sku_id: int = Field(title="SKU ID", description="SKU ID")
    sku_name: str = Field(title="SKU名称", description="SKU名称")
    face_value: Decimal = Field(title="面值", description="面值")
    bonus_amount: Decimal = Field(title="赠送金额", description="赠送金额")
    actual_amount: Decimal = Field(title="实际售价", description="实际售价")
    quantity: int = Field(title="数量", description="数量")
    created_at: datetime = Field(title="创建时间", description="创建时间")
    updated_at: datetime = Field(title="更新时间", description="更新时间")


class CartListResponse(BaseModel):
    """购物车分页列表"""

    model_config = {"title": "购物车列表响应"}

    items: list[CartItemInfo] = Field(title="购物车列表", description="购物车列表")
    total: int = Field(title="总数", description="总数")
    page: int = Field(title="当前页码", description="当前页码")
    page_size: int = Field(title="每页数量", description="每页数量")


class CartUpdateRequest(BaseModel):
    """修改购物车数量请求参数"""

    model_config = {"title": "修改购物车数量请求"}

    quantity: int = Field(..., ge=1, title="数量", description="数量，不小于1")
