"""Thin wrapper around the shared Messenger-Platform-style send (channels/common.py) — kept as
its own module so Messenger-specific behavior has a natural place to live without touching the
shared code, mirroring channels/instagram/client.py.
"""

from reply_agent.channels.common import send_page_message

send_text_message = send_page_message
