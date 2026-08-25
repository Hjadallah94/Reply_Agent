"""Password hashing — bcrypt directly (not passlib: passlib is unmaintained and its bcrypt
backend has had version-detection bugs with recent bcrypt releases; the bcrypt package alone is
all this needs).
"""

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
