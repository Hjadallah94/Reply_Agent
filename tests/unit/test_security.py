from reply_agent.auth.security import hash_password, verify_password


def test_verify_password_accepts_the_correct_password():
    password_hash = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", password_hash) is True


def test_verify_password_rejects_the_wrong_password():
    password_hash = hash_password("correct horse battery staple")
    assert verify_password("wrong password", password_hash) is False


def test_hash_password_does_not_store_the_plaintext():
    password_hash = hash_password("correct horse battery staple")
    assert "correct horse battery staple" not in password_hash


def test_hash_password_is_salted_differently_each_time():
    first = hash_password("same password")
    second = hash_password("same password")
    assert first != second
