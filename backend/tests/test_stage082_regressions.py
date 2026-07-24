from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import unittest
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "stage082_regressions.sqlite3"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.test_stage06 import BackendHarness, FakeOllamaClient


class Stage082RegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = DB_PATH
        if self.db_path.exists():
            self.db_path.unlink()
        self.harness = BackendHarness(self.db_path)

    def tearDown(self) -> None:
        self.harness.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_generation_limit_is_reported_and_partial_answer_stays_incomplete(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage082-length", "secret")
        self.harness.login("stage082-length", "secret")
        chat = client.post("/api/chats", json={}).json()

        fake_ollama: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_ollama.response_queue = [[
            json.dumps({"message": {"content": "hel"}, "done": False}),
            json.dumps({"message": {"content": "lo"}, "done": True, "done_reason": "length"}),
        ]]

        body = asyncio.run(self.harness.run_chat(alice.id, chat["id"], "Hello"))

        self.assertIn('"type": "error"', body)
        self.assertNotIn('"type": "done"', body)
        self.assertFalse(self.harness.main.app.state.active_chat_generations)

        with Session(self.harness.db.engine) as db:
            messages = db.exec(
                text("SELECT role, content, is_complete FROM messages WHERE chat_id = :chat_id ORDER BY id"),
                params={"chat_id": chat["id"]},
            ).all()
            self.assertEqual(messages[0][0], "user")
            self.assertEqual(messages[1][0], "assistant")
            self.assertEqual(messages[1][1], "hello")
            self.assertEqual(messages[1][2], 0)

    def test_web_search_mode_persists_per_user_and_survives_reload(self) -> None:
        legacy_harness = None
        legacy_db_path = self.db_path.parent / "stage082_regressions_legacy.sqlite3"
        if legacy_db_path.exists():
            legacy_db_path.unlink()

        with sqlite3.connect(legacy_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(64) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                ("stage082-user-a", "hash", "2026-07-23 00:00:00"),
            )
            conn.commit()

        try:
            legacy_harness = BackendHarness(legacy_db_path)
            client = legacy_harness.client
            assert client is not None

            with Session(legacy_harness.db.engine) as db:
                user = db.exec(
                    text("SELECT id FROM users WHERE username = :username"),
                    params={"username": "stage082-user-a"},
                ).first()
                assert user is not None
                db.exec(
                    text("UPDATE users SET password_hash = :password_hash WHERE id = :id"),
                    params={
                        "id": user[0],
                        "password_hash": legacy_harness.security.hash_password("secret"),
                    },
                )
                db.commit()

            legacy_harness.login("stage082-user-a", "secret")
            me = client.get("/api/auth/me")
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["web_search_mode"], "off")
            self.assertEqual(me.json()["web_search_provider"], "duckduckgo")

            updated = client.patch("/api/auth/me", json={"web_search_mode": "always"})
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["web_search_mode"], "always")
            self.assertEqual(updated.json()["web_search_provider"], "duckduckgo")
            self.assertEqual(client.get("/api/auth/me").json()["web_search_mode"], "always")

            legacy_harness.create_user("stage082-user-b", "secret")
            legacy_harness.login("stage082-user-b", "secret")
            me_b = client.get("/api/auth/me").json()
            self.assertEqual(me_b["web_search_mode"], "off")
            self.assertEqual(me_b["web_search_provider"], "duckduckgo")

            legacy_harness.reload_same_db()
            client = legacy_harness.client
            assert client is not None
            legacy_harness.login("stage082-user-a", "secret")
            self.assertEqual(client.get("/api/auth/me").json()["web_search_mode"], "always")
            self.assertEqual(client.get("/api/auth/me").json()["web_search_provider"], "duckduckgo")
        finally:
            if legacy_harness is not None:
                legacy_harness.close()

    def test_web_search_provider_defaults_and_persists_in_sqlite(self) -> None:
        client = self.harness.client
        assert client is not None

        self.harness.create_user("stage082-provider", "secret")
        self.harness.login("stage082-provider", "secret")

        me = client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["web_search_provider"], "duckduckgo")

        updated = client.patch("/api/auth/me", json={"web_search_provider": "duckduckgo"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["web_search_provider"], "duckduckgo")

        with Session(self.harness.db.engine) as db:
            row = db.exec(
                text("SELECT web_search_provider FROM users WHERE username = :username"),
                params={"username": "stage082-provider"},
            ).first()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "duckduckgo")

    def test_long_history_keeps_current_message_once(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage082-history", "secret")
        self.harness.login("stage082-history", "secret")
        chat = client.post("/api/chats", json={"context_message_limit": 40}).json()

        fake_ollama: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_ollama.response_queue = [[json.dumps({"message": {"content": "ok"}, "done": True})]] * 22

        for turn in range(1, 21):
            asyncio.run(self.harness.run_chat(alice.id, chat["id"], f"turn {turn}"))

        asyncio.run(self.harness.run_chat(alice.id, chat["id"], "turn 21"))

        request = fake_ollama.captured_requests[-1]
        serialized_messages = json.dumps(request["messages"], ensure_ascii=False)

        self.assertEqual(serialized_messages.count("turn 21"), 1)
        self.assertNotIn('"content": ""', serialized_messages)
        self.assertLessEqual(len(request["messages"]) - 1, 40)


if __name__ == "__main__":
    unittest.main()
