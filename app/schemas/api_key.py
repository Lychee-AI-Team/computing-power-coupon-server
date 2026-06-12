from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    """创建 API Key 请求"""

    model_config = {"title": "创建API Key请求"}

    name: str = Field(..., min_length=1, max_length=64, title="名称", description="Key 名称, 用于业务备注区分")
    expired_at: datetime | None = Field(default=None, title="过期时间", description="NULL 或省略表示永不过期")


class ApiKeyUpdateRequest(BaseModel):
    """更新 API Key 请求, 仅传入需要修改的字段"""

    model_config = {"title": "更新API Key请求"}

    name: str | None = Field(default=None, min_length=1, max_length=64, title="名称", description="Key 名称")
    status: int | None = Field(default=None, ge=0, le=1, title="状态", description="0=禁用, 1=启用")
    expired_at: datetime | None = Field(default=None, title="过期时间", description="显式传 null 视为重置为永不过期")


class ApiKeyInfo(BaseModel):
    """API Key 详情(不含明文)"""

    model_config = {"title": "API Key信息", "from_attributes": True}

    id: int = Field(title="Key ID")
    name: str = Field(title="名称")
    key_prefix: str = Field(title="展示前缀", description="sk_+前8位hex, 用于列表展示")
    status: int = Field(title="状态", description="0=禁用, 1=启用")
    expired_at: datetime | None = Field(default=None, title="过期时间")
    last_used_at: datetime | None = Field(default=None, title="最近使用时间")
    created_at: datetime = Field(title="创建时间")
    updated_at: datetime = Field(title="更新时间")


class ApiKeyCreateResponse(ApiKeyInfo):
    """创建 API Key 的响应, 仅此一次返回 raw_key"""

    model_config = {"title": "API Key创建响应", "from_attributes": True}

    raw_key: str = Field(title="原始Key", description="API Key 明文, 仅在创建时返回, 请妥善保存")


class ApiKeyListResponse(BaseModel):
    """API Key 分页列表响应"""

    model_config = {"title": "API Key列表响应"}

    items: list[ApiKeyInfo] = Field(title="API Key列表")
    total: int = Field(title="总数")
    page: int = Field(title="当前页码")
    page_size: int = Field(title="每页数量")


class ExternalCouponItem(BaseModel):
    """外部接口返回的未兑换券项"""

    model_config = {"title": "未兑换算力券项"}

    item_id: int = Field(title="订单项ID")
    order_id: int = Field(title="订单ID")
    order_no: str = Field(title="订单号")
    sku_id: int = Field(title="SKU ID")
    sku_name: str = Field(title="SKU名称")
    face_value: Decimal = Field(title="面值")
    actual_amount: Decimal = Field(title="实际额度")
    redemption_code: str = Field(title="兑换码")
    expired_at: datetime | None = Field(default=None, title="过期时间")
    created_at: datetime = Field(title="创建时间")


class ExternalCouponListResponse(BaseModel):
    """外部接口返回的未兑换券分页列表"""

    model_config = {"title": "未兑换算力券列表响应"}

    items: list[ExternalCouponItem] = Field(title="未兑换券列表")
    total: int = Field(title="总数")
    page: int = Field(title="当前页码")
    page_size: int = Field(title="每页数量")
