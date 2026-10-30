from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import SESSION_COOKIE, decode_token
from app.models import User


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    payload = decode_token(token) if token else None
    if not payload:
        raise HTTPException(401, "Please sign in.")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active or not user.can_login:
        raise HTTPException(401, "Please sign in.")
    return user


def require_role(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "You do not have access to this area.")
        return user

    return dep


worker_only = require_role("worker")
officer_only = require_role("officer")
admin_only = require_role("admin")
officer_or_admin = require_role("officer", "admin")


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""
