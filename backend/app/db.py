from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import DATABASE_PATH
from app.core.time import utc_now
from app.models.behavior_profile import BehaviorProfile
from app.models.chat import Chat
from app.models.memory import MemoryItem
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
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_memory_items_user_id ON memory_items (user_id)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_memory_items_is_active ON memory_items (is_active)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_memory_items_updated_at ON memory_items (updated_at)")
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


def _ensure_chat_context_message_limit_column() -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        chat_columns = {column["name"] for column in inspector.get_columns("chats")}
        if "context_message_limit" not in chat_columns:
            connection.execute(
                text(
                    "ALTER TABLE chats ADD COLUMN context_message_limit INTEGER "
                    "NOT NULL DEFAULT 40"
                )
            )
        connection.execute(
            text(
                "UPDATE chats "
                "SET context_message_limit = 40 "
                "WHERE context_message_limit IS NULL"
            )
        )


def _ensure_chat_summary_columns() -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        chat_columns = {column["name"] for column in inspector.get_columns("chats")}

        if "context_summary" not in chat_columns:
            connection.execute(
                text("ALTER TABLE chats ADD COLUMN context_summary TEXT")
            )
        if "summary_through_message_id" not in chat_columns:
            connection.execute(
                text("ALTER TABLE chats ADD COLUMN summary_through_message_id INTEGER")
            )
        if "summary_updated_at" not in chat_columns:
            connection.execute(
                text("ALTER TABLE chats ADD COLUMN summary_updated_at DATETIME")
            )


def _ensure_message_is_complete_column() -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        message_columns = {column["name"] for column in inspector.get_columns("messages")}
        if "is_complete" not in message_columns:
            connection.execute(
                text("ALTER TABLE messages ADD COLUMN is_complete BOOLEAN NOT NULL DEFAULT 1")
            )
        connection.execute(
            text(
                "UPDATE messages "
                "SET is_complete = 1 "
                "WHERE is_complete IS NULL"
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


def _prune_orphan_memory_items() -> None:
    with Session(engine) as session:
        memory_items = session.exec(select(MemoryItem)).all()
        changed = False
        for memory in memory_items:
            user_exists = session.exec(
                text("SELECT 1 FROM users WHERE id = :user_id"),
                params={"user_id": memory.user_id},
            ).first()
            if user_exists is None:
                session.delete(memory)
                changed = True
        if changed:
            session.commit()


def init_db() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    _ensure_chat_profile_column()
    _ensure_chat_context_message_limit_column()
    _ensure_chat_summary_columns()
    _ensure_message_is_complete_column()
    _ensure_sqlite_indexes()
    _backfill_behavior_profiles()
    _prune_orphan_memory_items()


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
