import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

SESSION_COOKIE = "es_session"
CSRF_COOKIE = "es_csrf"
CSRF_HEADER = "X-CSRF-Token"
PASSWORD_RULE = "At least 10 characters, with at least one letter and one number."


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def password_ok(password: str) -> bool:
    return len(password) >= 10 and re.search(r"[A-Za-z]", password) is not None and re.search(r"\d", password) is not None


def create_token(user_id: int, role: str) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": now + timedelta(hours=s.session_hours)}
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


class RateLimiter:
    """Fixed-window in-memory limiter, keyed by client IP and route."""

    def __init__(self, limit: int, window_s: int):
        self.limit = limit
        self.window_s = window_s
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window_s:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True

    def reset(self) -> None:
        self.hits.clear()


auth_limiter = RateLimiter(limit=10, window_s=60)
