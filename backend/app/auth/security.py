import hashlib
import secrets

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

password_hash = PasswordHash.recommended()
# Unknown-email logins still run Argon2id so response time does not reveal account existence.
_DUMMY_PASSWORD_HASH = password_hash.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str | None) -> bool:
    stored_hash = encoded_hash or _DUMMY_PASSWORD_HASH
    try:
        verified = password_hash.verify(password, stored_hash)
        return encoded_hash is not None and verified
    except (UnknownHashError, ValueError, TypeError):
        return False


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    # The raw token is only sent to the browser; PostgreSQL stores its digest.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
