from __future__ import annotations

import asyncio
import importlib
import json
import os
import sqlite3
import sys
import unittest
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlmodel import Session, select


BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "stage06.sqlite3"


class FakeResponse:
    def __init__(self, lines: list[str], delay: float = 0.0) -> None:
        self.lines = lines
        self.delay = delay

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        for line in self.lines:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield line


class FakeOllamaClient:
    def __init__(self, base_url: str, default_model: str) -> None:
        self.base_url = base_url
        self.default_model = default_model
        self.available_models = [{"name": default_model}]
        self.lines = [json.dumps({"message": {"content": "ok"}, "done": True})]
        self.response_queue: list[list[str]] = []
        self.delay = 0.0
        self.fail_stream = None
        self.captured_requests: list[dict] = []

    async def aclose(self) -> None:
        return None

    async def list_models(self) -> list[dict]:
        return self.available_models

    async def ensure_model_available(self, model: str) -> None:
        if not any(item.get("name") == model for item in self.available_models):
            raise RuntimeError(f"Model '{model}' is unavailable")

    async def switch_active_model(self, current_model: str, next_model: str) -> str:
        return next_model

    @asynccontextmanager
    async def stream_chat(self, model: str, messages: list[dict], think: bool):
        self.captured_requests.append(
            {"model": model, "messages": messages, "think": think}
        )
        if self.fail_stream is not None:
            raise self.fail_stream
        lines = self.response_queue.pop(0) if self.response_queue else self.lines
        yield FakeResponse(lines, self.delay)

    async def iter_content(self, response: FakeResponse):
        from app.clients.ollama import OllamaStreamEndedWithoutDoneError

        seen_done = False
        async for line in response.aiter_lines():
            if not line:
                continue
            payload = json.loads(line)
            content = payload.get("message", {}).get("content")
            if content:
                yield content
            if payload.get("done"):
                seen_done = True
                break
        if not seen_done:
            raise OllamaStreamEndedWithoutDoneError("Ollama stream ended before done=true.")


class BackendHarness:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.client: TestClient | None = None
        self.main = None
        self.db = None
        self.auth = None
        self.profiles = None
        self.chats = None
        self.chat_route = None
        self.behavior = None
        self.chat_models = None
        self.memory = None
        self.security = None
        self.model_manager = None
        self._load()

    def close(self) -> None:
        if self.client is not None:
            self.client.__exit__(None, None, None)
            self.client = None
        if self.db is not None:
            self.db.engine.dispose()

    def reload_same_db(self) -> None:
        self.close()
        self._load()

    def _load(self) -> None:
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        os.environ["SERVE_FRONTEND"] = "false"
        os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
        os.environ["OLLAMA_DEFAULT_MODEL"] = "test-model"

        self.main = importlib.import_module("app.main")
        self.main.OllamaClient = FakeOllamaClient
        self.db = importlib.import_module("app.db")
        self.auth = importlib.import_module("app.routers.auth")
        self.profiles = importlib.import_module("app.routers.profiles")
        self.chats = importlib.import_module("app.routers.chats")
        self.chat_route = importlib.import_module("app.routers.chat")
        self.behavior = importlib.import_module("app.models.behavior_profile")
        self.chat_models = importlib.import_module("app.models.chat")
        self.memory = importlib.import_module("app.models.memory")
        self.security = importlib.import_module("app.core.security")
        self.model_manager = importlib.import_module("app.services.model_manager")

        self.client = TestClient(self.main.app)
        self.client.__enter__()
        self.main.app.state.model_manager = self.model_manager.ModelManager(
            self.main.app.state.ollama_client,
            "test-model",
        )

    def create_user(self, username: str, password: str):
        with Session(self.db.engine) as db:
            user = self.auth.create_user(db, username, password)
            db.refresh(user)
            return SimpleNamespace(id=user.id, username=user.username)

    def login(self, username: str, password: str) -> None:
        assert self.client is not None
        self.client.cookies.clear()
        response = self.client.post("/api/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.text

    def insert_profile(
        self,
        owner_id: int,
        name: str,
        description: str,
        instructions: str,
        is_default: bool = False,
    ):
        with Session(self.db.engine) as db:
            profile = self.behavior.BehaviorProfile(
                owner_id=owner_id,
                name=name,
                description=description,
                instructions=instructions,
                is_default=is_default,
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)
            return profile

    def insert_chat(
        self,
        owner_id: int,
        title: str,
        profile_id: int | None = None,
        context_message_limit: int = 40,
    ):
        with Session(self.db.engine) as db:
            chat = self.chat_models.Chat(
                user_id=owner_id,
                profile_id=profile_id,
                title=title,
                context_message_limit=context_message_limit,
            )
            db.add(chat)
            db.commit()
            db.refresh(chat)
            return chat

    def insert_memory(self, user_id: int, content: str, is_active: bool = True):
        with Session(self.db.engine) as db:
            memory = self.memory.MemoryItem(
                user_id=user_id,
                content=content,
                is_active=is_active,
            )
            db.add(memory)
            db.commit()
            db.refresh(memory)
            return memory

    def get_user(self, user_id: int):
        with Session(self.db.engine) as db:
            return db.get(self.auth.User, user_id)

    def query_messages(self, chat_id: int):
        with Session(self.db.engine) as db:
            return db.exec(
                select(self.chat_models.Message)
                .where(self.chat_models.Message.chat_id == chat_id)
                .order_by(self.chat_models.Message.id)
            ).all()

    def make_fake_request(self, disconnect_after: int | None = None):
        calls = {"count": 0}

        class FakeRequest:
            def __init__(self, app):
                self.app = app

            async def is_disconnected(self):
                calls["count"] += 1
                if disconnect_after is None:
                    return False
                return calls["count"] > disconnect_after

        return FakeRequest(self.main.app)

    async def run_chat(self, user_id: int, chat_id: int, content: str, disconnect_after: int | None = None):
        request = self.make_fake_request(disconnect_after=disconnect_after)
        payload = self.chat_models.ChatTurnRequest(chat_id=chat_id, content=content, mode="instant")
        with Session(self.db.engine) as db:
            current_user = db.get(self.auth.User, user_id)
            response = await self.chat_route.chat(
                request=request,
                payload=payload,
                current_user=current_user,
                db=db,
            )
            body = await self.consume_stream(response)
        return body

    async def consume_stream(self, response) -> str:
        parts: list[str] = []
        async for chunk in response.body_iterator:
            parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))
        return "".join(parts)


class Stage06Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = DB_PATH
        if self.db_path.exists():
            self.db_path.unlink()
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

    def test_auth_and_default_profile(self) -> None:
        client = self.harness.client
        assert client is not None

        self.assertEqual(client.get("/api/profiles").status_code, 401)
        self.assertEqual(client.post("/api/profiles", json={}).status_code, 401)
        self.assertEqual(client.get("/api/profiles/1").status_code, 401)
        self.assertEqual(client.patch("/api/profiles/1", json={"name": "x"}).status_code, 401)
        self.assertEqual(client.delete("/api/profiles/1").status_code, 401)

        self.harness.create_user("alice", "secret")
        self.harness.login("alice", "secret")
        profiles = client.get("/api/profiles")
        self.assertEqual(profiles.status_code, 200)
        self.assertEqual(len(profiles.json()), 1)
        self.assertTrue(profiles.json()[0]["is_default"])

    def test_migration_backfills_existing_data(self) -> None:
        self.harness.close()
        if self.db_path.exists():
            self.db_path.unlink()
        self.create_legacy_db()
        self.harness.reload_same_db()
        client = self.harness.client
        assert client is not None

        login = client.post("/api/auth/login", json={"username": "legacy", "password": "legacy-pass"})
        self.assertEqual(login.status_code, 200)

        profiles = client.get("/api/profiles")
        self.assertEqual(profiles.status_code, 200)
        self.assertEqual(len(profiles.json()), 1)

        chats = client.get("/api/chats")
        self.assertEqual(chats.status_code, 200)
        self.assertEqual(len(chats.json()), 1)
        chat_summary = chats.json()[0]
        self.assertIsNotNone(chat_summary["profile_id"])
        self.assertEqual(chat_summary["context_message_limit"], 40)
        self.assertEqual(len(client.get(f"/api/chats/{chat_summary['id']}").json()["messages"]), 1)

    def test_profile_isolation_validation_and_default_switch(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("alice", "secret")
        bob = self.harness.create_user("bob", "secret")
        self.harness.login("alice", "secret")

        created = client.post(
            "/api/profiles",
            json={"name": "Alice helper", "description": "", "instructions": "Be concise."},
        )
        self.assertEqual(created.status_code, 201)

        bob_profile = self.harness.insert_profile(bob.id, "Bob helper", "Bob desc", "Bob instructions")
        bob_chat = self.harness.insert_chat(bob.id, "Bob chat", bob_profile.id)

        visible_names = [item["name"] for item in client.get("/api/profiles").json()]
        self.assertNotIn("Bob helper", visible_names)
        self.assertEqual(client.get(f"/api/profiles/{bob_profile.id}").status_code, 404)
        self.assertEqual(client.get(f"/api/chats/{bob_chat.id}").status_code, 404)

        self.assertEqual(client.post("/api/profiles", json={"name": "", "instructions": "x"}).status_code, 422)
        self.assertEqual(client.post("/api/profiles", json={"name": "x", "instructions": ""}).status_code, 422)
        self.assertEqual(client.post("/api/profiles", json={"name": "x" * 121, "instructions": "ok"}).status_code, 422)
        self.assertEqual(
            client.post("/api/profiles", json={"name": "x", "description": "d" * 241, "instructions": "ok"}).status_code,
            422,
        )
        self.assertEqual(client.post("/api/profiles", json={"name": "x", "instructions": "i" * 8001}).status_code, 422)

        new_default = client.post(
            "/api/profiles",
            json={
                "name": "Replacement",
                "description": "Alt",
                "instructions": "Alt instructions",
                "is_default": True,
            },
        )
        self.assertEqual(new_default.status_code, 201)
        profiles = client.get("/api/profiles").json()
        defaults = [item for item in profiles if item["is_default"]]
        self.assertEqual(len(defaults), 1)
        self.assertEqual(defaults[0]["name"], "Replacement")
        self.assertEqual(client.delete(f"/api/profiles/{defaults[0]['id']}").status_code, 409)

    def test_chat_profile_assignment_and_history_preserved(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("alice", "secret")
        bob = self.harness.create_user("bob", "secret")
        self.harness.login("alice", "secret")

        alice_profile = client.post(
            "/api/profiles",
            json={"name": "Alice profile", "description": "A", "instructions": "Alice instructions"},
        ).json()
        default_profile = client.get("/api/profiles").json()[0]
        bob_profile = self.harness.insert_profile(bob.id, "Bob profile", "B", "Bob instructions")

        chat_default = client.post("/api/chats", json={}).json()
        self.assertEqual(chat_default["profile_id"], default_profile["id"])

        chat_custom = client.post("/api/chats", json={"profile_id": alice_profile["id"]}).json()
        self.assertEqual(chat_custom["profile_id"], alice_profile["id"])
        self.assertEqual(client.post("/api/chats", json={"profile_id": bob_profile.id}).status_code, 404)
        self.assertEqual(
            client.patch(f"/api/chats/{chat_custom['id']}", json={"profile_id": bob_profile.id}).status_code,
            404,
        )

        before = client.get(f"/api/chats/{chat_custom['id']}").json()
        self.assertEqual(before["messages"], [])
        self.assertEqual(
            client.patch(f"/api/chats/{chat_custom['id']}", json={"profile_id": alice_profile["id"]}).status_code,
            200,
        )
        after = client.get(f"/api/chats/{chat_custom['id']}").json()
        self.assertEqual(after["profile_id"], alice_profile["id"])
        self.assertEqual(after["messages"], [])

        used_profile = client.post(
            "/api/profiles",
            json={"name": "Used", "instructions": "Used instructions"},
        ).json()
        client.post("/api/chats", json={"profile_id": used_profile["id"]})
        self.assertEqual(client.delete(f"/api/profiles/{used_profile['id']}").status_code, 409)

    def test_chat_context_message_limit_round_trip_and_history_window(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("alice", "secret")
        self.harness.login("alice", "secret")

        created = client.post("/api/chats", json={"context_message_limit": 10})
        self.assertEqual(created.status_code, 201)
        chat = created.json()
        self.assertEqual(chat["context_message_limit"], 10)

        self.assertEqual(client.patch(f"/api/chats/{chat['id']}", json={"context_message_limit": 9}).status_code, 422)
        self.assertEqual(client.patch(f"/api/chats/{chat['id']}", json={"context_message_limit": 101}).status_code, 422)

        updated = client.patch(f"/api/chats/{chat['id']}", json={"context_message_limit": 11})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["context_message_limit"], 11)
        self.assertEqual(client.get(f"/api/chats/{chat['id']}").json()["context_message_limit"], 11)

        restored = client.patch(f"/api/chats/{chat['id']}", json={"context_message_limit": 10})
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["context_message_limit"], 10)

        fake_client = self.harness.main.app.state.ollama_client
        fake_client.lines = [json.dumps({"message": {"content": "one"}, "done": True})]

        for turn in range(1, 6):
            asyncio.run(self.harness.run_chat(alice.id, chat["id"], f"turn {turn}"))

        asyncio.run(self.harness.run_chat(alice.id, chat["id"], "turn 6"))

        sixth_request = fake_client.captured_requests[-1]

        self.assertEqual(
            [message["role"] for message in sixth_request["messages"]],
            ["system", "user", "assistant", "user", "assistant", "user", "assistant", "user", "assistant", "user"],
        )
        self.assertIn("turn 2", sixth_request["messages"][1]["content"])
        self.assertNotIn("turn 1", json.dumps(sixth_request["messages"], ensure_ascii=False))

        messages = self.harness.query_messages(chat["id"])
        self.assertEqual(
            [message.role for message in messages],
            [
                "user",
                "assistant",
                "user",
                "assistant",
                "user",
                "assistant",
                "user",
                "assistant",
                "user",
                "assistant",
                "user",
                "assistant",
            ],
        )

    def test_stream_prompt_partial_response_and_lock_release(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("alice", "secret")
        self.harness.login("alice", "secret")
        profile = client.post(
            "/api/profiles",
            json={
                "name": "Storyteller",
                "description": "Narrative",
                "instructions": "Use a vivid style.",
                "is_default": True,
            },
        ).json()
        chat = client.post("/api/chats", json={"profile_id": profile["id"]}).json()

        fake_client = self.harness.main.app.state.ollama_client
        fake_client.lines = [
            json.dumps({"message": {"content": "hel"}, "done": False}),
            json.dumps({"message": {"content": "lo"}, "done": True}),
        ]
        fake_client.delay = 0.01

        body = asyncio.run(self.harness.run_chat(alice.id, chat["id"], "Hi there", disconnect_after=1))
        self.assertIn('"type": "content"', body)
        self.assertNotIn('"type": "done"', body)

        messages = self.harness.query_messages(chat["id"])
        self.assertEqual([message.role for message in messages], ["user", "assistant"])
        self.assertEqual(messages[-1].content, "hel")
        self.assertFalse(messages[-1].is_complete)

        chat_detail = client.get(f"/api/chats/{chat['id']}")
        self.assertEqual(chat_detail.status_code, 200)
        self.assertEqual(chat_detail.json()["messages"][-1]["content"], "hel")
        self.assertFalse(chat_detail.json()["messages"][-1]["is_complete"])

        captured = fake_client.captured_requests[-1]
        self.assertEqual(captured["model"], "test-model")
        self.assertEqual(captured["messages"][0]["role"], "system")
        self.assertIn("Use a vivid style.", captured["messages"][0]["content"])
        self.assertNotIn("role\": \"system\"", body)

        fake_client.fail_stream = RuntimeError("boom")
        error_body = asyncio.run(self.harness.run_chat(alice.id, chat["id"], "Again"))
        self.assertIn('"type": "error"', error_body)

        fake_client.fail_stream = None
        fake_client.lines = [json.dumps({"message": {"content": "ok"}, "done": True})]
        done_body = asyncio.run(self.harness.run_chat(alice.id, chat["id"], "One more"))
        self.assertIn('"type": "done"', done_body)

        updated = client.patch(
            f"/api/profiles/{profile['id']}",
            json={"instructions": "Switch to a calmer tone."},
        ).json()
        self.assertEqual(updated["instructions"], "Switch to a calmer tone.")

        fake_client.lines = [json.dumps({"message": {"content": "next"}, "done": True})]
        asyncio.run(self.harness.run_chat(alice.id, chat["id"], "After update"))
        self.assertIn("Switch to a calmer tone.", fake_client.captured_requests[-1]["messages"][0]["content"])

    def test_stream_prompt_eof_without_done_keeps_partial_assistant_incomplete(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("alice", "secret")
        self.harness.login("alice", "secret")
        chat = client.post("/api/chats", json={}).json()

        fake_client = self.harness.main.app.state.ollama_client
        fake_client.lines = [
            json.dumps({"message": {"content": "hel"}, "done": False}),
            json.dumps({"message": {"content": "lo"}}),
        ]

        body = asyncio.run(self.harness.run_chat(alice.id, chat["id"], "Hi there"))
        self.assertIn('"type": "error"', body)
        self.assertNotIn('"type": "done"', body)

        messages = self.harness.query_messages(chat["id"])
        self.assertEqual([message.role for message in messages], ["user", "assistant"])
        self.assertEqual(messages[-1].content, "hello")
        self.assertFalse(messages[-1].is_complete)

    def test_restarted_app_restores_selected_profile(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("alice", "secret")
        self.harness.login("alice", "secret")
        profile = client.post(
            "/api/profiles",
            json={"name": "Profile A", "description": "A", "instructions": "Instr"},
        ).json()
        chat = client.post("/api/chats", json={"profile_id": profile["id"]}).json()

        self.harness.reload_same_db()
        client = self.harness.client
        assert client is not None
        self.harness.login("alice", "secret")
        restored = client.get(f"/api/chats/{chat['id']}").json()
        self.assertEqual(restored["profile_id"], profile["id"])


if __name__ == "__main__":
    unittest.main()
