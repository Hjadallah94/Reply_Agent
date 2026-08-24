"""Messenger Platform webhook (Doc 2 Section 2.1, Doc 3 Phase 2). Shares its parsing/dedup/
enqueue logic with Instagram Messaging via channels/common.py — re-verify the "object": "page"
check and payload shape against Meta's current Messenger Platform docs before go-live, same
caveat as the WhatsApp client.
"""

from reply_agent.channels.common import build_messaging_webhook_router
from reply_agent.db.models import ChannelType

router = build_messaging_webhook_router(
    channel=ChannelType.messenger, prefix="/webhooks/messenger", expected_object="page"
)
