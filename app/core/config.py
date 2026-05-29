from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_DEBUG: bool = False
    APP_PORT: int = 8000

    # MySQL
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "computing_power_coupon"

    # Redis
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    # External Platform
    EXTERNAL_PLATFORM_BASE_URL: str = ""
    EXTERNAL_PLATFORM_ADMIN_TOKEN: str = ""
    EXTERNAL_PLATFORM_ADMIN_ID: str = ""

    # Exchange API
    EXCHANGE_API_SECRET_KEY: str = ""
    EXCHANGE_TOKEN_MAX_AGE_SECONDS: int = 0  # 0 = 永久有效

    # WeChat Pay V3
    WECHAT_APPID: str = ""
    WECHAT_MCH_ID: str = ""
    WECHAT_API_V3_KEY: str = ""
    WECHAT_PRIVATE_KEY: str = ""
    WECHAT_MCH_SERIAL_NO: str = ""
    WECHAT_PUBLIC_KEY: str = ""
    WECHAT_NOTIFY_URL: str = ""

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    @property
    def mysql_dsn(self) -> str:
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{quote_plus(self.MYSQL_PASSWORD)}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{quote_plus(self.REDIS_PASSWORD)}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
