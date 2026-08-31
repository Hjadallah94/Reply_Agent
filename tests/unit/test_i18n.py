from reply_agent.i18n import TRANSLATIONS, t, t_status


def test_t_returns_the_requested_language():
    key = next(iter(TRANSLATIONS))
    assert t("en", key) == TRANSLATIONS[key]["en"]
    assert t("ar", key) == TRANSLATIONS[key]["ar"]


def test_t_falls_back_to_english_for_a_missing_language_entry():
    assert t("fr", "base.logout") == TRANSLATIONS["base.logout"]["en"]


def test_t_falls_back_to_the_raw_key_for_an_unknown_key():
    assert t("en", "nonexistent.key") == "nonexistent.key"
    assert t("ar", "nonexistent.key") == "nonexistent.key"


def test_t_status_translates_a_known_status_value():
    assert t_status("ar", "in_stock") == TRANSLATIONS["status.in_stock"]["ar"]
    assert t_status("en", "in_stock") == TRANSLATIONS["status.in_stock"]["en"]


def test_t_status_falls_back_to_the_raw_value_for_an_unrecognized_status():
    """stock_status is genuinely free text — a seller's own custom value must display
    unchanged, not as a literal "status.<value>" translation-key string.
    """
    assert t_status("ar", "backordered") == "backordered"
    assert t_status("en", "backordered") == "backordered"
