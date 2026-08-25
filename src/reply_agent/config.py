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
    # Our own Tech Provider System User token (Business Settings > System Users), shared across
    # every onboarded business — not a per-number token. Meta grants it access to each customer's
    # WABA as they complete Embedded Signup (onboarding/whatsapp_signup.py), so one value here
    # covers every connected business's outbound sends (channels/whatsapp/client.py).
    whatsapp_access_token: str = ""
    # Only our own demo/dev business's number — real businesses' numbers live in their own
    # Business.channels_connected["whatsapp"]["phone_number_id"], not here.
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_webhook_verify_token: str = "change-me"
    meta_graph_api_version: str = "v21.0"
    # "Facebook Login for Business" > Configurations entry using the WhatsApp Embedded Signup
    # template (App Dashboard, created once manually — see README). Required for
    # onboarding/whatsapp_signup.py's frontend trigger page to work at all.
    meta_embedded_signup_config_id: str = ""

    # Instagram Messaging and Messenger Platform are both accessed via the connected Facebook
    # Page — the same one shared System User token (see whatsapp_access_token above) works
    # across every connected business's Page once Facebook Login for Business grants it access
    # (onboarding/page_signup.py), not a separate token per business.
    meta_page_access_token: str = ""
    meta_webhook_verify_token: str = "change-me"
    # A second, separate "Facebook Login for Business" Configuration (App Dashboard) — this one
    # targeting Page + Instagram account assets with pages_messaging/instagram_manage_messages,
    # not the WhatsApp Embedded Signup template used by meta_embedded_signup_config_id above.
    meta_page_signup_config_id: str = ""

    owner_notification_whatsapp_number: str = ""

    # When true, every channel's send function logs instead of calling the real Graph API —
    # used by the eval harness and local dev before real Meta credentials exist.
    meta_dry_run: bool = False

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
