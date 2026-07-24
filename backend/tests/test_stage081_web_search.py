from __future__ import annotations

import asyncio
import json
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "stage081_web_search.sqlite3"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.clients.duckduckgo import DuckDuckGoSearchResult
from app.models.web_search import MessageSource
from tests.test_stage06 import BackendHarness, FakeOllamaClient


@dataclass
class FakeDuckDuckGoClient:
    results: list[DuckDuckGoSearchResult]
    failure: Exception | None = None

    def __post_init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def aclose(self) -> None:
        return None

    async def search(self, query: str, max_results: int = 5) -> list[DuckDuckGoSearchResult]:
        self.calls.append({"query": query, "max_results": max_results})
        if self.failure is not None:
            raise self.failure
        return self.results[:max_results]


class Stage081WebSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = DB_PATH
        if self.db_path.exists():
            self.db_path.unlink()
        self.harness = BackendHarness(self.db_path)

    def tearDown(self) -> None:
        self.harness.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_web_search_off_does_not_call_duckduckgo(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage081-off", "secret")
        self.harness.login("stage081-off", "secret")
        chat = client.post("/api/chats", json={}).json()

        fake_search = FakeDuckDuckGoClient(
            results=[
                DuckDuckGoSearchResult(
                    position=1,
                    title="Example result",
                    url="https://example.com",
                    snippet="A useful summary.",
                    page_excerpt="Page excerpt",
                )
            ]
        )
        self.harness.main.app.state.web_search_client = fake_search

        fake_ollama: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_ollama.response_queue = [[json.dumps({"message": {"content": "ok"}, "done": True})]]

        asyncio.run(self.harness.run_chat(alice.id, chat["id"], "What is new?"))

        self.assertEqual(fake_search.calls, [])
        request = fake_ollama.captured_requests[0]
        self.assertNotIn("Web search results", request["messages"][0]["content"])

    def test_web_search_on_persists_sources_and_injects_context(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage081-on", "secret")
        self.harness.login("stage081-on", "secret")
        chat = client.post("/api/chats", json={}).json()

        fake_search = FakeDuckDuckGoClient(
            results=[
                DuckDuckGoSearchResult(
                    position=1,
                    title="OpenAI Docs",
                    url="https://example.com/openai",
                    snippet="Documentation for the API.",
                    page_excerpt="Reference page excerpt.",
                ),
                DuckDuckGoSearchResult(
                    position=2,
                    title="Second source",
                    url="https://example.com/second",
                    snippet="Another helpful snippet.",
                    page_excerpt=None,
                ),
            ]
        )
        self.harness.main.app.state.web_search_client = fake_search

        fake_ollama: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_ollama.response_queue = [[json.dumps({"message": {"content": "answer"}, "done": True})]]

        asyncio.run(
            self.harness.run_chat(
                alice.id,
                chat["id"],
                "What changed in the docs?",
                use_web_search=True,
            )
        )

        self.assertEqual(len(fake_search.calls), 1)
        self.assertEqual(fake_search.calls[0]["query"], "What changed in the docs?")

        request = fake_ollama.captured_requests[0]
        system_prompt = request["messages"][0]["content"]
        self.assertIn("Web search results", system_prompt)
        self.assertIn("OpenAI Docs", system_prompt)
        self.assertIn("Reference page excerpt.", system_prompt)

        chat_detail = client.get(f"/api/chats/{chat['id']}")
        self.assertEqual(chat_detail.status_code, 200)
        assistant_messages = [
            message for message in chat_detail.json()["messages"] if message["role"] == "assistant"
        ]
        self.assertEqual(len(assistant_messages), 1)
        self.assertEqual(len(assistant_messages[0]["sources"]), 2)
        self.assertEqual(assistant_messages[0]["sources"][0]["position"], 1)
        self.assertEqual(assistant_messages[0]["sources"][0]["title"], "OpenAI Docs")
        self.assertEqual(assistant_messages[0]["sources"][1]["position"], 2)

        with Session(self.harness.db.engine) as db:
            sources = db.exec(select(MessageSource)).all()
            self.assertEqual(len(sources), 2)
            self.assertEqual([source.position for source in sources], [1, 2])

    def test_search_error_creates_no_assistant_message_or_sources(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage081-search-fail", "secret")
        self.harness.login("stage081-search-fail", "secret")
        chat = client.post("/api/chats", json={}).json()

        fake_search = FakeDuckDuckGoClient(results=[], failure=RuntimeError("search failed"))
        self.harness.main.app.state.web_search_client = fake_search

        fake_ollama: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_ollama.response_queue = [[json.dumps({"message": {"content": "ignored"}, "done": True})]]

        body = asyncio.run(
            self.harness.run_chat(alice.id, chat["id"], "What changed?", use_web_search=True)
        )

        self.assertIn('"type": "error"', body)
        self.assertEqual(fake_search.calls[0]["query"], "What changed?")

        with Session(self.harness.db.engine) as db:
            messages = db.exec(
                select(self.harness.chat_models.Message).where(
                    self.harness.chat_models.Message.chat_id == chat["id"]
                )
            ).all()
            self.assertEqual([message.role for message in messages], ["user"])
            self.assertEqual(db.exec(select(MessageSource)).all(), [])

    def test_ollama_error_after_search_leaves_no_orphan_sources_and_recovers(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage081-ollama-fail", "secret")
        self.harness.login("stage081-ollama-fail", "secret")
        chat = client.post("/api/chats", json={}).json()

        with Session(self.harness.db.engine) as db:
            stored_chat = db.get(self.harness.chat_models.Chat, chat["id"])
            assert stored_chat is not None
            stored_chat.context_summary = "Keep this summary."
            db.add(stored_chat)
            db.commit()

            memory = self.harness.memory.MemoryItem(
                user_id=alice.id,
                content="Remember the tea.",
                is_active=True,
            )
            db.add(memory)
            db.commit()

        fake_search = FakeDuckDuckGoClient(
            results=[
                DuckDuckGoSearchResult(
                    position=1,
                    title="OpenAI Docs",
                    url="https://example.com/openai",
                    snippet="Documentation for the API.",
                    page_excerpt="Reference page excerpt.",
                )
            ]
        )
        self.harness.main.app.state.web_search_client = fake_search

        fake_ollama: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_ollama.fail_stream = RuntimeError("boom")

        body = asyncio.run(
            self.harness.run_chat(alice.id, chat["id"], "What changed?", use_web_search=True)
        )

        self.assertIn('"type": "error"', body)

        with Session(self.harness.db.engine) as db:
            stored_chat = db.get(self.harness.chat_models.Chat, chat["id"])
            assert stored_chat is not None
            self.assertEqual(stored_chat.context_summary, "Keep this summary.")
            memories = db.exec(select(self.harness.memory.MemoryItem)).all()
            self.assertEqual(len(memories), 1)
            self.assertEqual(memories[0].content, "Remember the tea.")
            self.assertEqual(db.exec(select(MessageSource)).all(), [])
            assistant_messages = db.exec(
                select(self.harness.chat_models.Message).where(
                    self.harness.chat_models.Message.chat_id == chat["id"],
                    self.harness.chat_models.Message.role == "assistant",
                )
            ).all()
            self.assertEqual(assistant_messages, [])

        fake_ollama.fail_stream = None
        fake_ollama.response_queue = [[json.dumps({"message": {"content": "ok"}, "done": True})]]
        retry_body = asyncio.run(
            self.harness.run_chat(alice.id, chat["id"], "Next question", use_web_search=False)
        )
        self.assertIn('"type": "done"', retry_body)

    def test_stop_after_search_releases_guard_and_does_not_persist_sources(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage081-stop", "secret")
        self.harness.login("stage081-stop", "secret")
        chat = client.post("/api/chats", json={}).json()

        fake_search = FakeDuckDuckGoClient(
            results=[
                DuckDuckGoSearchResult(
                    position=1,
                    title="OpenAI Docs",
                    url="https://example.com/openai",
                    snippet="Documentation for the API.",
                    page_excerpt="Reference page excerpt.",
                )
            ]
        )
        self.harness.main.app.state.web_search_client = fake_search

        fake_ollama: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_ollama.response_queue = [[
            json.dumps({"message": {"content": "hel"}, "done": False}),
            json.dumps({"message": {"content": "lo"}, "done": True}),
        ]]
        fake_ollama.delay = 0.01

        body = asyncio.run(
            self.harness.run_chat(
                alice.id,
                chat["id"],
                "Need fresh info",
                disconnect_after=1,
                use_web_search=True,
            )
        )

        self.assertIn('"type": "content"', body)
        self.assertNotIn('"type": "done"', body)
        self.assertFalse(self.harness.main.app.state.active_chat_generations)

        with Session(self.harness.db.engine) as db:
            messages = db.exec(
                select(self.harness.chat_models.Message)
                .where(self.harness.chat_models.Message.chat_id == chat["id"])
                .order_by(self.harness.chat_models.Message.id)
            ).all()
            self.assertEqual([message.role for message in messages], ["user", "assistant"])
            self.assertFalse(messages[-1].is_complete)
            self.assertEqual(db.exec(select(MessageSource)).all(), [])

    def test_message_source_cascade_on_chat_delete_and_message_delete(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage081-cascade", "secret")
        self.harness.login("stage081-cascade", "secret")
        chat = client.post("/api/chats", json={}).json()

        fake_search = FakeDuckDuckGoClient(
            results=[
                DuckDuckGoSearchResult(
                    position=1,
                    title="OpenAI Docs",
                    url="https://example.com/openai",
                    snippet="Documentation for the API.",
                    page_excerpt="Reference page excerpt.",
                )
            ]
        )
        self.harness.main.app.state.web_search_client = fake_search

        fake_ollama: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_ollama.response_queue = [[json.dumps({"message": {"content": "done"}, "done": True})]]

        asyncio.run(
            self.harness.run_chat(alice.id, chat["id"], "Need fresh info", use_web_search=True)
        )

        with Session(self.harness.db.engine) as db:
            message = db.exec(
                select(self.harness.chat_models.Message)
                .where(self.harness.chat_models.Message.chat_id == chat["id"])
                .where(self.harness.chat_models.Message.role == "assistant")
            ).first()
            assert message is not None
            db.delete(message)
            db.commit()
            self.assertEqual(db.exec(select(MessageSource)).all(), [])

        fake_ollama.response_queue = [[json.dumps({"message": {"content": "done"}, "done": True})]]
        asyncio.run(
            self.harness.run_chat(alice.id, chat["id"], "Need fresh info again", use_web_search=True)
        )
        self.assertEqual(client.delete(f"/api/chats/{chat['id']}").status_code, 204)

        with Session(self.harness.db.engine) as db:
            self.assertEqual(
                db.exec(
                    select(self.harness.chat_models.Message)
                    .where(self.harness.chat_models.Message.chat_id == chat["id"])
                ).all(),
                [],
            )
            self.assertEqual(db.exec(select(MessageSource)).all(), [])


if __name__ == "__main__":
    unittest.main()
