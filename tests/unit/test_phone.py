from reply_agent.orders.phone import normalize_phone


def test_already_normalized_is_unchanged():
    assert normalize_phone("962791234567") == "962791234567"


def test_local_leading_zero_gets_country_code():
    assert normalize_phone("0791234567") == "962791234567"


def test_plus_prefix_is_stripped():
    assert normalize_phone("+962791234567") == "962791234567"


def test_00_prefix_is_stripped():
    assert normalize_phone("00962791234567") == "962791234567"


def test_excel_stripped_leading_zero_is_recovered():
    # Common Excel gotcha: a phone column formatted as a number drops the leading 0.
    assert normalize_phone("791234567") == "962791234567"


def test_dashes_and_spaces_are_stripped():
    assert normalize_phone("07 9123-4567") == "962791234567"


def test_non_jordanian_looking_number_is_left_alone():
    assert normalize_phone("12025551234") == "12025551234"
