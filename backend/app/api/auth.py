from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import client_ip, current_user
from app.core.security import (CSRF_COOKIE, PASSWORD_RULE, SESSION_COOKIE, auth_limiter, create_token, decode_token,
                               hash_password, new_csrf_token, password_ok, verify_password)
from app.models import User, WorkerProfile
from app.schemas import LoginIn, RegisterIn
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(user: User) -> dict:
    out = {"id": user.id, "email": user.email, "name": user.name, "role": user.role,
           "preferred_language": user.preferred_language, "lender": None, "profile": None}
    if user.lender:
        out["lender"] = {"id": user.lender.id, "name": user.lender.name}
    if user.profile:
        p = user.profile
        out["profile"] = {"city": p.city, "work_type": p.work_type, "languages": p.languages,
                          "group_attr": p.group_attr, "group_attr_consent": p.group_attr_consent,
                          "training_consent": p.training_consent}
    return out


def _set_session(response: Response, user: User) -> None:
    s = get_settings()
    response.set_cookie(SESSION_COOKIE, create_token(user.id, user.role), httponly=True, secure=s.is_production,
                        samesite="lax", max_age=s.session_hours * 3600, path="/")
    response.set_cookie(CSRF_COOKIE, new_csrf_token(), httponly=False, secure=s.is_production, samesite="strict",
                        max_age=s.session_hours * 3600, path="/")


def _limit(request: Request) -> None:
    if not auth_limiter.allow(f"{client_ip(request)}:{request.url.path}"):
        raise HTTPException(429, "Too many attempts. Please wait a minute and try again.")


@router.get("/csrf")
def csrf(response: Response, request: Request):
    token = request.cookies.get(CSRF_COOKIE) or new_csrf_token()
    response.set_cookie(CSRF_COOKIE, token, httponly=False, secure=get_settings().is_production, samesite="strict", path="/")
    return {"csrf": token}


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _limit(request)
    if not password_ok(body.password):
        raise HTTPException(422, PASSWORD_RULE)
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists. Try signing in.")
    user = User(email=email, password_hash=hash_password(body.password), name=body.name.strip(), role="worker",
                preferred_language=body.preferred_language)
    user.profile = WorkerProfile(city=body.city, work_type=body.work_type, languages=list(body.languages))
    db.add(user)
    db.flush()
    audit(db, user.id, "user.register", "user", user.id, ip=client_ip(request))
    db.commit()
    _set_session(response, user)
    return user_out(user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _limit(request)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not user.can_login or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    if not user.is_active:
        raise HTTPException(403, "This account has been deactivated. Contact support.")
    audit(db, user.id, "user.login", "user", user.id, ip=client_ip(request))
    db.commit()
    _set_session(response, user)
    return user_out(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/session")
def session(request: Request, db: Session = Depends(get_db)):
    """Who is signed in, or null. Lets the app check the session without an error response."""
    token = request.cookies.get(SESSION_COOKIE)
    payload = decode_token(token) if token else None
    user = db.get(User, int(payload["sub"])) if payload else None
    if not user or not user.is_active or not user.can_login:
        return {"user": None}
    return {"user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)
