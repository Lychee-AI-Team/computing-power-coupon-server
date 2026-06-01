from pydantic import BaseModel, Field


class UserRegisterRequest(BaseModel):
    """用户注册请求参数"""

    model_config = {"title": "用户注册请求"}

    username: str = Field(..., min_length=1, max_length=20, title="用户名", description="用户名，长度 ≤ 20")
    password: str = Field(..., min_length=8, max_length=20, title="密码", description="密码，长度 8-20")


class UserLoginRequest(BaseModel):
    """用户登录请求参数"""

    model_config = {"title": "用户登录请求"}

    username: str = Field(title="用户名", description="用户名")
    password: str = Field(title="密码", description="密码")


class TokenResponse(BaseModel):
    """登录成功后返回的访问令牌"""

    model_config = {"title": "令牌响应"}

    access_token: str = Field(title="访问令牌", description="访问令牌")
    token_type: str = Field(default="bearer", title="令牌类型", description="令牌类型")


class UserSearchItem(BaseModel):
    """用户搜索结果中的单个用户信息"""

    model_config = {"title": "用户搜索项"}

    id: int = Field(title="用户ID", description="用户ID")
    username: str = Field(title="用户名", description="用户名")


class UserSearchResponse(BaseModel):
    """用户搜索结果"""

    model_config = {"title": "用户搜索响应"}

    users: list[UserSearchItem] = Field(title="用户列表", description="用户列表")


class ChangePasswordRequest(BaseModel):
    """修改密码请求参数"""

    model_config = {"title": "修改密码请求"}

    new_password: str = Field(..., min_length=8, max_length=20, title="新密码", description="新密码，长度 8-20")


class MessageResponse(BaseModel):
    """操作结果消息"""

    model_config = {"title": "通用消息响应"}

    message: str = Field(title="操作结果", description="操作结果信息")


class CurrentUserResponse(BaseModel):
    """当前登录用户信息"""

    model_config = {"title": "当前用户信息"}

    id: int = Field(title="用户ID", description="用户ID")
    username: str = Field(title="用户名", description="用户名")
    role: int = Field(title="角色", description="角色，1-普通用户 10-管理员 100-超级管理员")


class WechatQrcodeRequest(BaseModel):
    """微信二维码生成请求"""

    model_config = {"title": "微信二维码请求"}

    mode: str = Field(default="login", title="模式", description="二维码模式，如 login")


class WechatQrcodeResponse(BaseModel):
    """微信二维码生成响应"""

    model_config = {"title": "微信二维码响应"}

    qrcode_url: str = Field(title="二维码URL", description="微信二维码图片URL")
    scene_str: str = Field(title="场景值", description="二维码场景字符串，用于轮询登录状态")


class WechatScanStatusRequest(BaseModel):
    """微信扫码登录状态查询请求"""

    model_config = {"title": "微信扫码状态请求"}

    scene_str: str = Field(title="场景值", description="生成二维码时返回的场景字符串")


class WechatScanStatusResponse(BaseModel):
    """微信扫码登录状态响应"""

    model_config = {"title": "微信扫码状态响应"}

    status: str = Field(title="扫码状态", description="pending-等待扫码 / confirmed-已确认 / expired-已过期 / error-错误")
    access_token: str | None = Field(default=None, title="访问令牌", description="confirmed 时返回的 JWT 令牌")
    token_type: str = Field(default="bearer", title="令牌类型", description="令牌类型")
