from __future__ import annotations

from datetime import datetime

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session, select

from app.core.config import SESSION_COOKIE_NAME
from app.core.time import utc_now
from app.db import get_db
from app.models.auth import Session as UserSession
from app.models.auth import User


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация.",
        )

    user_session = db.get(UserSession, session_token)
    if not user_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация.",
        )

    now = utc_now()
    if user_session.expires_at <= now:
        db.delete(user_session)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия истекла. Войдите снова.",
        )

    user = db.exec(select(User).where(User.id == user_session.user_id)).first()
    if not user:
        db.delete(user_session)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация.",
        )

    return user
