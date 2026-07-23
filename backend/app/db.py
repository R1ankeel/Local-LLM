from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import DATABASE_PATH
from app.core.time import utc_now
from app.models.behavior_profile import BehaviorProfile
from app.models.chat import Chat
from app.services.behavior_profiles import ensure_default_profile


DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


def _ensure_sqlite_indexes() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_behavior_profiles_owner_id "
                "ON behavior_profiles (owner_id)"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_behavior_profiles_owner_default "
                "ON behavior_profiles (owner_id) WHERE is_default = 1"
            )
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_chats_profile_id ON chats (profile_id)")
        )


def _ensure_chat_profile_column() -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        chat_columns = {column["name"] for column in inspector.get_columns("chats")}
        if "profile_id" not in chat_columns:
            connection.execute(
                text(
                    "ALTER TABLE chats ADD COLUMN profile_id INTEGER "
                    "REFERENCES behavior_profiles(id)"
                )
            )


def _backfill_behavior_profiles() -> None:
    with Session(engine) as session:
        user_ids = [row[0] for row in session.exec(text("SELECT id FROM users")).all()]
        for user_id in user_ids:
            ensure_default_profile(session, user_id)

        chats = session.exec(select(Chat)).all()
        changed = False
        for chat in chats:
            profile = None
            if chat.profile_id is not None:
                profile = session.get(BehaviorProfile, chat.profile_id)

            if profile is None or profile.owner_id != chat.user_id:
                default_profile = ensure_default_profile(session, chat.user_id)
                chat.profile_id = default_profile.id
                chat.updated_at = utc_now()
                changed = True

        if changed:
            session.add_all(chats)
            session.commit()


def init_db() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    _ensure_chat_profile_column()
    _ensure_sqlite_indexes()
    _backfill_behavior_profiles()


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
