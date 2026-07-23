from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, SQLModel, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "stage081.sqlite3"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.test_stage06 import BackendHarness, FakeOllamaClient


class Stage081MemoryTests(unittest.TestCase):
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
            conn.commit()
        finally:
            conn.close()

    def seed_memory(self, user_id: int, content: str, *, is_active: bool = True, updated_at: datetime | None = None):
        with Session(self.harness.db.engine) as db:
            memory = self.harness.memory.MemoryItem(
                user_id=user_id,
                content=content,
                is_active=is_active,
                created_at=updated_at or datetime.utcnow().replace(microsecond=0),
                updated_at=updated_at or datetime.utcnow().replace(microsecond=0),
            )
            db.add(memory)
            db.commit()
            db.refresh(memory)
            return memory

    def test_migration_adds_memory_items_without_losing_existing_data(self) -> None:
        self.harness.close()
        if self.db_path.exists():
            self.db_path.unlink()
        self.create_legacy_db()
        self.harness.reload_same_db()
        client = self.harness.client
        assert client is not None

        login = client.post("/api/auth/login", json={"username": "legacy", "password": "legacy-pass"})
        self.assertEqual(login.status_code, 200)

        with Session(self.harness.db.engine) as db:
            tables = {
                row[0]
                for row in db.exec(
                    text("SELECT name FROM sqlite_master WHERE type = 'table'")
                ).all()
            }
            self.assertIn("memory_items", tables)
            self.assertEqual(db.exec(select(self.harness.memory.MemoryItem)).all(), [])

        memories = client.get("/api/memories")
        self.assertEqual(memories.status_code, 200)
        self.assertEqual(memories.json(), [])

    def test_memory_crud_and_isolation(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("alice", "secret")
        bob = self.harness.create_user("bob", "secret")
        self.harness.login("alice", "secret")

        created = client.post("/api/memories", json={"content": "  Remember the tea  "})
        self.assertEqual(created.status_code, 201)
        memory = created.json()
        self.assertEqual(memory["content"], "Remember the tea")
        self.assertTrue(memory["is_active"])

        self.assertEqual(client.post("/api/memories", json={"content": ""}).status_code, 422)
        self.assertEqual(client.post("/api/memories", json={"content": "x" * 501}).status_code, 422)
        self.assertEqual(
            client.post("/api/memories", json={"content": "ok", "user_id": bob.id}).status_code,
            422,
        )

        bob_memory = self.harness.insert_memory(bob.id, "Bob secret")
        self.assertEqual(client.get("/api/memories").json()[0]["content"], "Remember the tea")
        self.assertEqual(client.patch(f"/api/memories/{bob_memory.id}", json={"content": "nope"}).status_code, 404)
        self.assertEqual(client.delete(f"/api/memories/{bob_memory.id}").status_code, 404)

        updated = client.patch(
            f"/api/memories/{memory['id']}",
            json={"content": "Remember the coffee", "is_active": False},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["content"], "Remember the coffee")
        self.assertFalse(updated.json()["is_active"])

        memories = client.get("/api/memories").json()
        self.assertEqual(memories[0]["content"], "Remember the coffee")

        self.assertEqual(client.delete(f"/api/memories/{memory['id']}").status_code, 204)
        self.assertEqual(client.get("/api/memories").json(), [])

    def test_memory_prompt_is_injected_without_duplicates_or_other_users(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("alice", "secret")
        bob = self.harness.create_user("bob", "secret")
        self.harness.login("alice", "secret")

        chat = client.post("/api/chats", json={}).json()
        self.harness.insert_memory(alice.id, "Keep answers concise.")
        self.harness.insert_memory(alice.id, "Prefer metric units.", is_active=False)
        self.harness.insert_memory(bob.id, "Bob memory should stay hidden.")

        fake_client: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_client.response_queue = [[json.dumps({"message": {"content": "ok"}, "done": True})]]

        asyncio.run(self.harness.run_chat(alice.id, chat["id"], "Hello"))

        request = fake_client.captured_requests[0]
        system_prompt = request["messages"][0]["content"]
        self.assertIn("Long-term memory", system_prompt)
        self.assertIn("Keep answers concise.", system_prompt)
        self.assertNotIn("Prefer metric units.", system_prompt)
        self.assertNotIn("Bob memory should stay hidden.", system_prompt)
        self.assertNotIn("system_note", system_prompt)

    def test_memory_prompt_prefers_recent_complete_entries_and_respects_budget(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("alice", "secret")
        self.harness.login("alice", "secret")
        chat = client.post("/api/chats", json={}).json()

        base_time = datetime.utcnow().replace(microsecond=0) - timedelta(days=1)
        for index in range(1, 11):
            content = f"memory-{index:02d} " + ("x" * 480)
            moment = base_time + timedelta(minutes=index)
            self.seed_memory(alice.id, content, updated_at=moment)

        fake_client: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_client.response_queue = [[json.dumps({"message": {"content": "ok"}, "done": True})]]

        asyncio.run(self.harness.run_chat(alice.id, chat["id"], "Hi"))

        request = fake_client.captured_requests[0]
        system_prompt = request["messages"][0]["content"]
        self.assertIn("memory-10", system_prompt)
        self.assertIn("memory-04", system_prompt)
        self.assertNotIn("memory-03", system_prompt)
        self.assertLess(system_prompt.index("memory-10"), system_prompt.index("memory-09"))
        self.assertLess(system_prompt.index("memory-09"), system_prompt.index("memory-08"))


if __name__ == "__main__":
    unittest.main()
