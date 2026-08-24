"""Thin wrapper around the shared Messenger-Platform-style send (channels/common.py) — kept as
its own module so Instagram-specific behavior (e.g. the 7-day human-agent tag window, which
differs from Messenger's rules) has a natural place to live without touching the shared code.
"""

from reply_agent.channels.common import send_page_message

send_text_message = send_page_message
