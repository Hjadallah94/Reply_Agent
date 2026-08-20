from functools import lru_cache

import anthropic

from reply_agent.config import get_settings

# Current Anthropic model IDs (verify against `client.models.list()` if this drifts).
MODEL_HAIKU = "claude-haiku-4-5"
MODEL_SONNET = "claude-sonnet-5"


@lru_cache
def get_anthropic_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
