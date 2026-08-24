"""Instagram Messaging webhook (Doc 2 Section 2.1, Doc 3 Phase 2). Shares its parsing/dedup/
enqueue logic with Messenger Platform via channels/common.py — re-verify the "object": "instagram"
check and payload shape against Meta's current Instagram Messaging docs before go-live, same
caveat as the WhatsApp client.
"""

from reply_agent.channels.common import build_messaging_webhook_router
from reply_agent.db.models import ChannelType

router = build_messaging_webhook_router(
    channel=ChannelType.instagram, prefix="/webhooks/instagram", expected_object="instagram"
)
