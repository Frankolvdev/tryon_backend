from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI Virtual Try-On Platform"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_VERSION: str = "0.1.0"

    API_V1_PREFIX: str = "/api/v1"

    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 55432
    POSTGRES_DB: str = "tryon_db"
    POSTGRES_USER: str = "tryon_user"
    POSTGRES_PASSWORD: str = "tryon_password"

    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 30
    DATABASE_POOL_TIMEOUT_SECONDS: int = 10
    DATABASE_POOL_RECYCLE_SECONDS: int = 1800

    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    STORAGE_PROVIDER: str = "local"
    LOCAL_STORAGE_DIR: str = "storage/local"

    TRYON_TOKENS_COST: int = 10

    COMFYUI_BASE_URL: str = "http://127.0.0.1:8188"
    COMFYUI_WORKFLOWS_DIR: str = "workflows"
    COMFYUI_POLL_TIMEOUT_SECONDS: int = 300
    COMFYUI_POLL_INTERVAL_SECONDS: float = 2.0

    RUNPOD_API_KEY: str | None = None
    RUNPOD_ENDPOINT_ID: str | None = None
    RUNPOD_BASE_URL: str = "https://api.runpod.ai/v2"
    RUNPOD_HTTP_TIMEOUT_SECONDS: float = 60.0
    RUNPOD_POLL_INTERVAL_SECONDS: float = 2.0
    RUNPOD_CALLBACK_URL: str | None = None
    RUNPOD_CALLBACK_SECRET: str | None = None

    WORKER_API_KEY: str | None = None

    METRICS_BACKGROUND_COLLECTION_ENABLED: bool = True
    METRICS_COLLECTION_INTERVAL_SECONDS: int = 30

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "AI Virtual Try-On"
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False

    TELEGRAM_BOT_TOKEN: str = ""

    SLACK_BOT_TOKEN: str = ""
    SLACK_WEBHOOK_URL: str = ""

    NOTIFICATION_HTTP_TIMEOUT_SECONDS: int = 20
    NOTIFICATION_MAX_ATTEMPTS: int = 5

    WEB_PUSH_VAPID_PRIVATE_KEY: str = ""
    WEB_PUSH_VAPID_PUBLIC_KEY: str = ""
    WEB_PUSH_VAPID_SUBJECT: str = ""

    USER_NOTIFICATION_EMAIL_ENABLED: bool = True
    USER_NOTIFICATION_WEB_PUSH_ENABLED: bool = True
    USER_NOTIFICATION_RETENTION_DAYS: int = 365
    USER_NOTIFICATION_ARCHIVED_RETENTION_DAYS: int = 90
    USER_NOTIFICATION_MAX_EMAIL_ATTEMPTS: int = 5

    I18N_CACHE_TTL_SECONDS: int = 300

    FRONTEND_URL: str = "http://localhost:3000"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:"
            f"{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL(self) -> str:
        return (
            f"redis://{self.REDIS_HOST}:"
            f"{self.REDIS_PORT}/{self.REDIS_DB}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
