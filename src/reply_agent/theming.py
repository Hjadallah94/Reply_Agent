"""Owner's light/dark mode preference (Doc 3 roadmap, dashboard redesign) — session-backed,
same shape as i18n.py's get_lang/SUPPORTED_LANGUAGES. Three states, not two: "system" (the
default — no explicit choice, base.html leaves data-theme unset so prefers-color-scheme alone
decides) or an explicit "light"/"dark" that overrides the OS preference either way.
"""

from fastapi import Request

THEME_OPTIONS = ("system", "light", "dark")
DEFAULT_THEME = "system"


def get_theme(request: Request) -> str:
    theme = request.session.get("theme", DEFAULT_THEME)
    return theme if theme in THEME_OPTIONS else DEFAULT_THEME
