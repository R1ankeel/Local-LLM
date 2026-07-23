from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlmodel import SQLModel, Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "stage072.sqlite3"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlmodel import select

from tests.test_stage06 import BackendHarness, FakeOllamaClient


class Stage072SummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = DB_PATH
        if self.db_path.exists():
            self.db_path.unlink()
        for module_name in list(sys.modules):
            if module_name == "app" or module_name.startswith("app."):
                sys.modules.pop(module_name, None)
        SQLModel.metadata.clear()
        self.harness = BackendHarness(self.db_path)

    def tearDown(self) -> None:
        self.harness.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def create_legacy_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(64) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at DATETIME NOT NULL
                );
                CREATE TABLE sessions (
                    id VARCHAR(128) PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    expires_at DATETIME NOT NULL
                );
                CREATE TABLE chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title VARCHAR(120) NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                );
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    role VARCHAR(16) NOT NULL,
                    content VARCHAR(8000) NOT NULL,
                    created_at DATETIME NOT NULL
                );
                """
            )
            password_hash = self.harness.security.hash_password("legacy-pass")
            now = datetime.utcnow().replace(microsecond=0).isoformat(sep=" ")
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                ("legacy", password_hash, now),
            )
            user_id = conn.execute("SELECT id FROM users WHERE username = 'legacy'").fetchone()[0]
            conn.execute(
                "INSERT INTO chats (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (user_id, "Legacy chat", now, now),
            )
            chat_id = conn.execute("SELECT id FROM chats WHERE user_id = ?", (user_id,)).fetchone()[0]
            conn.execute(
                "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, "user", "hello", now),
            )
            conn.commit()
        finally:
            conn.close()

    def seed_messages(self, chat_id: int, count: int, include_system_note: bool = False) -> None:
        with Session(self.harness.db.engine) as db:
            for index in range(1, count + 1):
                role = "user" if index % 2 else "assistant"
                db.add(
                    self.harness.chat_models.Message(
                        chat_id=chat_id,
                        role=role,
                        content=f"seed {index}",
                    )
                )
                if include_system_note and index == 10:
                    db.execute(
                        text(
                            "INSERT INTO messages (chat_id, role, content, is_complete, created_at) "
                            "VALUES (:chat_id, :role, :content, :is_complete, :created_at)"
                        ),
                        {
                            "chat_id": chat_id,
                            "role": "system",
                            "content": "system-note",
                            "is_complete": 1,
                            "created_at": datetime.utcnow().replace(microsecond=0).isoformat(sep=" "),
                        },
                    )
            db.commit()

    def test_migration_adds_summary_columns_without_losing_data(self) -> None:
        self.harness.close()
        if self.db_path.exists():
            self.db_path.unlink()
        self.create_legacy_db()
        self.harness.reload_same_db()
        client = self.harness.client
        assert client is not None

        login = client.post("/api/auth/login", json={"username": "legacy", "password": "legacy-pass"})
        self.assertEqual(login.status_code, 200)

        chats = client.get("/api/chats")
        self.assertEqual(chats.status_code, 200)
        self.assertEqual(len(chats.json()), 1)
        chat = chats.json()[0]
        self.assertFalse(chat["has_context_summary"])
        self.assertIsNone(chat["summary_updated_at"])

        detail = client.get(f"/api/chats/{chat['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.json()["has_context_summary"])
        self.assertIsNone(detail.json()["summary_updated_at"])
        self.assertNotIn("context_summary", detail.json())

        with Session(self.harness.db.engine) as db:
            stored_chat = db.get(self.harness.chat_models.Chat, chat["id"])
            assert stored_chat is not None
            self.assertIsNone(stored_chat.context_summary)
            self.assertIsNone(stored_chat.summary_through_message_id)
            self.assertIsNone(stored_chat.summary_updated_at)
            stored_message = db.exec(
                select(self.harness.chat_models.Message)
                .where(self.harness.chat_models.Message.chat_id == chat["id"])
            ).first()
            assert stored_message is not None
            self.assertTrue(stored_message.is_complete)

    def test_new_chat_starts_without_summary(self) -> None:
        client = self.harness.client
        assert client is not None

        self.harness.create_user("alice", "secret")
        self.harness.login("alice", "secret")

        created = client.post("/api/chats", json={})
        self.assertEqual(created.status_code, 201)
        chat = created.json()
        self.assertFalse(chat["has_context_summary"])
        self.assertIsNone(chat["summary_updated_at"])

    def test_summary_does_not_run_before_threshold(self) -> None:
        client = self.harness.client
        assert client is not None

        user = self.harness.create_user("alice", "secret")
        self.harness.login("alice", "secret")

        chat = client.post("/api/chats", json={"context_message_limit": 10}).json()
        self.seed_messages(chat["id"], 19, include_system_note=True)

        fake_client: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_client.response_queue = [[json.dumps({"message": {"content": "ok"}, "done": True})]]

        asyncio.run(self.harness.run_chat(user.id, chat["id"], "current turn"))

        self.assertEqual(len(fake_client.captured_requests), 1)
        chat_request = fake_client.captured_requests[0]
        self.assertEqual(chat_request["messages"][0]["role"], "system")
        self.assertNotIn("Conversation summary", chat_request["messages"][0]["content"])
        self.assertNotIn("system-note", json.dumps(chat_request["messages"], ensure_ascii=False))
        self.assertIn("current turn", json.dumps(chat_request["messages"], ensure_ascii=False))

        with Session(self.harness.db.engine) as db:
            stored_chat = db.get(self.harness.chat_models.Chat, chat["id"])
            assert stored_chat is not None
            self.assertIsNone(stored_chat.context_summary)
            self.assertIsNone(stored_chat.summary_through_message_id)
            self.assertIsNone(stored_chat.summary_updated_at)

    def test_summary_waits_for_raw_window_and_skips_20_and_59_messages(self) -> None:
        client = self.harness.client
        assert client is not None

        self.harness.create_user("alice", "secret")
        self.harness.login("alice", "secret")
        fake_client: FakeOllamaClient = self.harness.main.app.state.ollama_client

        for count, expected_raw_count in ((20, 20), (59, 39)):
            with self.subTest(count=count):
                chat = client.post("/api/chats", json={"context_message_limit": 40}).json()
                self.seed_messages(chat["id"], count)

                with Session(self.harness.db.engine) as db:
                    stored_chat = db.get(self.harness.chat_models.Chat, chat["id"])
                    assert stored_chat is not None
                    updated = asyncio.run(
                        self.harness.chat_route._maybe_update_chat_summary(
                            db,
                            stored_chat,
                            fake_client,
                            "test-model",
                        )
                    )
                    self.assertFalse(updated)
                    self.assertIsNone(stored_chat.summary_through_message_id)
                    raw_messages = self.harness.chat_route._limited_messages(db, stored_chat)
                    self.assertEqual(len(raw_messages), expected_raw_count)
                    if count == 59:
                        self.assertEqual(raw_messages[0]["role"], "user")

    def test_summary_updates_one_batch_at_sixty_messages(self) -> None:
        client = self.harness.client
        assert client is not None

        self.harness.create_user("alice", "secret")
        self.harness.login("alice", "secret")
        chat = client.post("/api/chats", json={"context_message_limit": 40}).json()
        self.seed_messages(chat["id"], 60, include_system_note=True)

        fake_client: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_client.response_queue = [[json.dumps({"message": {"content": "summary-one"}, "done": True})]]

        with Session(self.harness.db.engine) as db:
            stored_chat = db.get(self.harness.chat_models.Chat, chat["id"])
            assert stored_chat is not None
            updated = asyncio.run(
                self.harness.chat_route._maybe_update_chat_summary(
                    db,
                    stored_chat,
                    fake_client,
                    "test-model",
                )
            )
            self.assertTrue(updated)

            summary_request = fake_client.captured_requests[0]
            self.assertIn("seed 1", summary_request["messages"][1]["content"])
            self.assertIn("seed 20", summary_request["messages"][1]["content"])
            self.assertNotIn("seed 21", summary_request["messages"][1]["content"])
            self.assertNotIn("system-note", summary_request["messages"][1]["content"])

            expected_through = db.exec(
                select(self.harness.chat_models.Message)
                .where(self.harness.chat_models.Message.chat_id == chat["id"])
                .where(self.harness.chat_models.Message.role.in_(("user", "assistant")))
                .order_by(self.harness.chat_models.Message.id)
            ).all()[19].id
            self.assertEqual(stored_chat.summary_through_message_id, expected_through)
            self.assertEqual(stored_chat.context_summary, "summary-one")

            raw_messages = self.harness.chat_route._limited_messages(db, stored_chat)
            self.assertEqual(len(raw_messages), 40)
            self.assertEqual(raw_messages[0]["role"], "user")
            self.assertEqual(raw_messages[0]["content"], "seed 21")
            self.assertEqual(raw_messages[-1]["content"], "seed 60")

    def test_summary_updates_one_batch_at_sixty_one_messages_and_keeps_partial_history(self) -> None:
        client = self.harness.client
        assert client is not None

        self.harness.create_user("alice", "secret")
        self.harness.login("alice", "secret")
        chat = client.post("/api/chats", json={"context_message_limit": 40}).json()
        self.seed_messages(chat["id"], 61, include_system_note=True)

        fake_client: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_client.response_queue = [[json.dumps({"message": {"content": "summary-one"}, "done": True})]]

        with Session(self.harness.db.engine) as db:
            stored_chat = db.get(self.harness.chat_models.Chat, chat["id"])
            assert stored_chat is not None
            updated = asyncio.run(
                self.harness.chat_route._maybe_update_chat_summary(
                    db,
                    stored_chat,
                    fake_client,
                    "test-model",
                )
            )
            self.assertTrue(updated)

            summary_request = fake_client.captured_requests[0]
            self.assertIn("seed 1", summary_request["messages"][1]["content"])
            self.assertIn("seed 20", summary_request["messages"][1]["content"])
            self.assertNotIn("seed 21", summary_request["messages"][1]["content"])
            self.assertNotIn("system-note", summary_request["messages"][1]["content"])

            expected_through = db.exec(
                select(self.harness.chat_models.Message)
                .where(self.harness.chat_models.Message.chat_id == chat["id"])
                .where(self.harness.chat_models.Message.role.in_(("user", "assistant")))
                .order_by(self.harness.chat_models.Message.id)
            ).all()[19].id
            self.assertEqual(stored_chat.summary_through_message_id, expected_through)

            raw_messages = self.harness.chat_route._limited_messages(db, stored_chat)
            self.assertEqual(len(raw_messages), 39)
            self.assertEqual(raw_messages[0]["role"], "user")
            self.assertEqual(raw_messages[0]["content"], "seed 23")
            self.assertEqual(raw_messages[-1]["content"], "seed 61")

    def test_partial_assistant_is_returned_to_frontend_but_not_summarized(self) -> None:
        client = self.harness.client
        assert client is not None

        self.harness.create_user("alice", "secret")
        self.harness.login("alice", "secret")
        chat = client.post("/api/chats", json={"context_message_limit": 40}).json()
        self.seed_messages(chat["id"], 60, include_system_note=True)

        with Session(self.harness.db.engine) as db:
            db.add(
                self.harness.chat_models.Message(
                    chat_id=chat["id"],
                    role="assistant",
                    content="partial assistant marker",
                    is_complete=False,
                )
            )
            db.commit()

        fake_client: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_client.response_queue = [[json.dumps({"message": {"content": "summary-one"}, "done": True})]]

        with Session(self.harness.db.engine) as db:
            stored_chat = db.get(self.harness.chat_models.Chat, chat["id"])
            assert stored_chat is not None
            updated = asyncio.run(
                self.harness.chat_route._maybe_update_chat_summary(
                    db,
                    stored_chat,
                    fake_client,
                    "test-model",
                )
            )
            self.assertTrue(updated)
            summary_request = fake_client.captured_requests[0]
            self.assertNotIn("partial assistant marker", summary_request["messages"][1]["content"])
            self.assertEqual(self.harness.chat_route._limited_messages(db, stored_chat)[0]["role"], "user")

        chat_detail = client.get(f"/api/chats/{chat['id']}")
        self.assertEqual(chat_detail.status_code, 200)
        self.assertEqual(chat_detail.json()["messages"][-1]["content"], "partial assistant marker")
        self.assertFalse(chat_detail.json()["messages"][-1]["is_complete"])


if __name__ == "__main__":
    unittest.main()
