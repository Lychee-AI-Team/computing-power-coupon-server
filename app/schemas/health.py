from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """服务健康检查结果"""

    model_config = {"title": "健康检查响应"}

    status: str = Field(title="服务状态", description="服务状态，ok-正常")
