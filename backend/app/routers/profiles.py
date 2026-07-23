from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import get_current_user
from app.models.auth import User
from app.models.behavior_profile import (
    BehaviorProfile,
    BehaviorProfileCreateRequest,
    BehaviorProfileRead,
    BehaviorProfileUpdateRequest,
)
from app.models.chat import Chat
from app.services.behavior_profiles import list_profiles, set_profile_as_default


router = APIRouter(prefix="/profiles")


def _get_owned_profile(db: Session, profile_id: int, user_id: int) -> BehaviorProfile:
    profile = db.get(BehaviorProfile, profile_id)
    if not profile or profile.owner_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Профиль не найден.")
    return profile


def _profile_read(profile: BehaviorProfile) -> BehaviorProfileRead:
    return BehaviorProfileRead.model_validate(profile)


@router.get("", response_model=list[BehaviorProfileRead])
def get_profiles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profiles = list_profiles(db, current_user.id)
    return [_profile_read(profile) for profile in profiles]


@router.post("", response_model=BehaviorProfileRead, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: BehaviorProfileCreateRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_default = db.exec(
        select(BehaviorProfile.id)
        .where(BehaviorProfile.owner_id == current_user.id)
        .where(BehaviorProfile.is_default.is_(True))
    ).first()
    make_default = payload.is_default or current_default is None

    profile = BehaviorProfile(
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
        instructions=payload.instructions,
        is_default=False,
    )
    db.add(profile)
    db.flush()
    if make_default:
        set_profile_as_default(db, profile)
    else:
        db.commit()
        db.refresh(profile)
    return _profile_read(profile)


@router.get("/{profile_id}", response_model=BehaviorProfileRead)
def get_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_owned_profile(db, profile_id, current_user.id)
    return _profile_read(profile)


@router.patch("/{profile_id}", response_model=BehaviorProfileRead)
def update_profile(
    profile_id: int,
    payload: BehaviorProfileUpdateRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_owned_profile(db, profile_id, current_user.id)
    changed = False

    if "name" in payload.model_fields_set and payload.name is not None:
        profile.name = payload.name
        changed = True
    if "description" in payload.model_fields_set and payload.description is not None:
        profile.description = payload.description
        changed = True
    if "instructions" in payload.model_fields_set and payload.instructions is not None:
        profile.instructions = payload.instructions
        changed = True

    if "is_default" in payload.model_fields_set and payload.is_default is not None:
        if payload.is_default:
            profile = set_profile_as_default(db, profile)
            changed = False
        elif profile.is_default:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя снять профиль по умолчанию, пока не назначен другой профиль по умолчанию.",
            )

    if changed:
        profile.updated_at = utc_now()
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _profile_read(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_owned_profile(db, profile_id, current_user.id)

    if profile.is_default:
        another_default = db.exec(
            select(BehaviorProfile.id)
            .where(BehaviorProfile.owner_id == current_user.id)
            .where(BehaviorProfile.id != profile.id)
            .where(BehaviorProfile.is_default.is_(True))
        ).first()
        if another_default is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Сначала назначьте другой профиль по умолчанию.",
            )

    used_by_chat = db.exec(select(Chat.id).where(Chat.profile_id == profile.id)).first()
    if used_by_chat is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нельзя удалить профиль, назначенный одному или нескольким чатам.",
        )

    db.delete(profile)
    db.commit()
    return None
