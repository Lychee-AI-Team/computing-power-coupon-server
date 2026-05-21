from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class SkuCreateRequest(BaseModel):
    """创建SKU商品请求参数"""

    model_config = {"title": "创建SKU请求"}

    sku_name: str = Field(..., min_length=1, max_length=100, title="SKU名称", description="SKU名称，1-100个字符")
    face_value: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2, title="面值", description="面值，必须大于0")
    bonus_amount: Decimal = Field(default=0, ge=0, max_digits=10, decimal_places=2, title="赠送金额", description="赠送金额，不小于0")
    actual_amount: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2, title="实际售价", description="实际售价，必须大于0")
    status: int = Field(default=1, ge=0, le=1, title="状态", description="状态，0-禁用 1-启用")
    expire_type: str = Field(default="day", pattern=r"^(day|month|year)$", title="过期类型", description="过期类型，day-天 month-月 year-年")
    expire_value: int = Field(default=90, ge=0, title="过期数值", description="过期数值，不小于0")


class SkuUpdateRequest(BaseModel):
    """更新SKU商品请求参数，所有字段可选"""

    model_config = {"title": "更新SKU请求"}

    sku_name: str | None = Field(default=None, min_length=1, max_length=100, title="SKU名称", description="SKU名称，1-100个字符")
    face_value: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2, title="面值", description="面值，必须大于0")
    bonus_amount: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2, title="赠送金额", description="赠送金额，不小于0")
    actual_amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2, title="实际售价", description="实际售价，必须大于0")
    status: int | None = Field(default=None, ge=0, le=1, title="状态", description="状态，0-禁用 1-启用")
    expire_type: str | None = Field(default=None, pattern=r"^(day|month|year)$", title="过期类型", description="过期类型，day-天 month-月 year-年")
    expire_value: int | None = Field(default=None, ge=0, title="过期数值", description="过期数值，不小于0")


class SkuItem(BaseModel):
    """SKU商品详细信息"""

    model_config = {"title": "SKU信息", "from_attributes": True}

    sku_id: int = Field(title="SKU ID", description="SKU ID")
    sku_name: str = Field(title="SKU名称", description="SKU名称")
    face_value: Decimal = Field(title="面值", description="面值")
    bonus_amount: Decimal = Field(title="赠送金额", description="赠送金额")
    actual_amount: Decimal = Field(title="实际售价", description="实际售价")
    status: int = Field(title="状态", description="状态，0-禁用 1-启用")
    expire_type: str = Field(title="过期类型", description="过期类型")
    expire_value: int = Field(title="过期数值", description="过期数值")
    created_at: datetime = Field(title="创建时间", description="创建时间")
    updated_at: datetime = Field(title="更新时间", description="更新时间")


class SkuListResponse(BaseModel):
    """SKU分页列表"""

    model_config = {"title": "SKU列表响应"}

    items: list[SkuItem] = Field(title="SKU列表", description="SKU列表")
    total: int = Field(title="总数", description="总数")
    page: int = Field(title="当前页码", description="当前页码")
    page_size: int = Field(title="每页数量", description="每页数量")


class SkuStatusRequest(BaseModel):
    """启用或禁用SKU"""

    model_config = {"title": "SKU状态变更请求"}

    status: int = Field(..., ge=0, le=1, title="状态", description="状态，0-禁用 1-启用")
