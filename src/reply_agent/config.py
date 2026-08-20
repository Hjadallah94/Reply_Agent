from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"

    database_url: str = "postgresql+asyncpg://reply_agent:reply_agent@localhost:5433/reply_agent"
    database_url_sync: str = (
        "postgresql+psycopg://reply_agent:reply_agent@localhost:5433/reply_agent"
    )

    redis_url: str = "redis://localhost:6380/0"

    anthropic_api_key: str = ""

    voyage_api_key: str = ""
    voyage_embedding_model: str = "voyage-3.5"

    meta_app_id: str = ""
    meta_app_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_webhook_verify_token: str = "change-me"
    meta_graph_api_version: str = "v21.0"

    owner_notification_whatsapp_number: str = ""

    # When true, send_text_message logs instead of calling the real Graph API — used by the
    # eval harness and local dev before real WhatsApp credentials exist.
    whatsapp_dry_run: bool = False

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
