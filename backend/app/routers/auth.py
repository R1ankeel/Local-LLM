from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, select

from app.core.config import SESSION_COOKIE_NAME, SESSION_TTL_DAYS
from app.core.time import utc_now
from app.core.security import generate_session_token, hash_password, verify_password
from app.db import get_db
from app.dependencies import get_current_user
from app.models.auth import LoginRequest, Session as UserSession, User, UserPublic
from app.services.behavior_profiles import ensure_default_profile


router = APIRouter(prefix="/auth")


def to_public_user(user: User) -> UserPublic:
    return UserPublic.model_validate(user)


def set_session_cookie(response: Response, token: str, expires_at) -> None:
    max_age = int((expires_at - utc_now()).total_seconds())
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
        max_age=max_age,
    )


@router.post("/login", response_model=UserPublic)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.exec(select(User).where(User.username == payload.username)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль.",
        )

    session_token = generate_session_token()
    expires_at = utc_now() + timedelta(days=SESSION_TTL_DAYS)
    db.add(
        UserSession(
            id=session_token,
            user_id=user.id,
            expires_at=expires_at,
        )
    )
    db.commit()
    set_session_cookie(response, session_token, expires_at)
    return to_public_user(user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        user_session = db.get(UserSession, session_token)
        if user_session:
            db.delete(user_session)
            db.commit()

    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/", samesite="lax")
    return {"ok": True}


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)):
    return to_public_user(current_user)


def create_user(db: Session, username: str, password: str) -> User:
    existing_user = db.exec(select(User).where(User.username == username)).first()
    if existing_user:
        raise ValueError(f"Пользователь '{username}' уже существует")

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    ensure_default_profile(db, user.id)
    return user
