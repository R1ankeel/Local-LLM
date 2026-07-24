from __future__ import annotations

import asyncio
import json
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "stage083_xai_web_search.sqlite3"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.clients.duckduckgo import DuckDuckGoSearchResult
from app.clients.xai import (
    XAIWebSearchClient,
    XAIWebSearchResult,
)
from tests.test_stage06 import BackendHarness, FakeOllamaClient


@dataclass
class FakeDuckDuckGoClient:
    results: list[DuckDuckGoSearchResult]
    block: bool = False

    def __post_init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def aclose(self) -> None:
        return None

    async def search(self, query: str, max_results: int = 5) -> list[DuckDuckGoSearchResult]:
        self.calls.append({"query": query, "max_results": max_results})
        self.started.set()
        if self.block:
            await self.release.wait()
        return self.results[:max_results]


@dataclass
class FakeXAIClient:
    results: list[XAIWebSearchResult]

    def __post_init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def aclose(self) -> None:
        return None

    async def search(self, query: str, max_results: int = 5) -> list[XAIWebSearchResult]:
        self.calls.append({"query": query, "max_results": max_results})
        return self.results[:max_results]


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class FakeHTTPClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def post(self, url: str, json: dict[str, object]) -> FakeHTTPResponse:
        self.calls.append({"url": url, "json": json})
        return FakeHTTPResponse(self.payload)

    async def aclose(self) -> None:
        return None


class Stage083XAIWebSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = DB_PATH
        if self.db_path.exists():
            self.db_path.unlink()
        self.harness = BackendHarness(self.db_path)

    def tearDown(self) -> None:
        self.harness.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_xai_client_parses_citations_and_annotations(self) -> None:
        client = XAIWebSearchClient(api_key="test-key", model="test-model", timeout_seconds=1)
        original_client = client._client
        fake_http = FakeHTTPClient(
            {
                "citations": [
                    "https://example.com/article",
                    {"url": "https://example.com/article", "title": "Duplicate title"},
                    {"url": "https://example.com/source", "title": "Source title"},
                ],
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Research summary for the query.",
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "url": "https://example.com/source",
                                        "title": "Annotated source",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )
        client._client = fake_http  # type: ignore[assignment]

        try:
            results = asyncio.run(client.search("  Search this  "))
        finally:
            asyncio.run(original_client.aclose())

        self.assertEqual(len(fake_http.calls), 1)
        self.assertEqual(fake_http.calls[0]["url"], "https://api.x.ai/v1/responses")
        payload = fake_http.calls[0]["json"]
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["store"], False)
        self.assertEqual(payload["include"], ["no_inline_citations"])
        self.assertEqual(payload["tools"], [{"type": "web_search"}])
        self.assertEqual(payload["input"][0]["content"], "Search this")

        self.assertEqual([result.url for result in results], ["https://example.com/article", "https://example.com/source"])
        self.assertEqual(results[0].title, "Duplicate title")
        self.assertEqual(results[1].title, "Annotated source")
        self.assertEqual(results[0].snippet, "Research summary for the query.")
        self.assertEqual(results[0].page_excerpt, "Research summary for the query.")

    def test_user_switches_provider_and_it_persists_in_sqlite(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage083-provider", "secret")
        self.harness.login("stage083-provider", "secret")

        me = client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["web_search_provider"], "duckduckgo")

        with Session(self.harness.db.engine) as db:
            user = db.exec(text("SELECT id, web_search_provider FROM users WHERE username = :username"), params={"username": "stage083-provider"}).first()
            self.assertIsNotNone(user)
            self.assertEqual(user[1], "duckduckgo")

        self.harness.web_search.XAI_API_KEY = "test-key"
        chat = client.post("/api/chats", json={}).json()
        updated = client.patch("/api/auth/me", json={"web_search_provider": "xai"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["web_search_provider"], "xai")

        with Session(self.harness.db.engine) as db:
            user = db.exec(text("SELECT web_search_provider FROM users WHERE username = :username"), params={"username": "stage083-provider"}).first()
            self.assertIsNotNone(user)
            self.assertEqual(user[0], "xai")

        fake_duck = FakeDuckDuckGoClient(
            results=[
                DuckDuckGoSearchResult(
                    position=1,
                    title="Duck result",
                    url="https://example.com/duck",
                    snippet="DuckDuckGo response.",
                    page_excerpt="DuckDuckGo page excerpt.",
                )
            ]
        )
        fake_xai = FakeXAIClient(
            results=[
                XAIWebSearchResult(
                    position=1,
                    title="xAI result",
                    url="https://x.ai/news",
                    snippet="xAI response.",
                    page_excerpt="xAI page excerpt.",
                )
            ]
        )
        self.harness.main.app.state.web_search_client = fake_duck
        self.harness.main.app.state.xai_web_search_client = fake_xai

        fake_ollama: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_ollama.response_queue = [[json.dumps({"message": {"content": "answer"}, "done": True})]]

        body = asyncio.run(
            self.harness.run_chat(
                alice.id,
                chat["id"],
                "What is the latest xAI update?",
                web_search_mode="always",
            )
        )

        self.assertEqual(fake_duck.calls, [])
        self.assertEqual(len(fake_xai.calls), 1)
        self.assertEqual(fake_xai.calls[0]["query"], "What is the latest xAI update?")
        self.assertIn('"type":"web_search_started"', body.replace(" ", ""))
        self.assertIn('"provider":"xai"', body.replace(" ", ""))

    def test_current_request_keeps_its_provider_when_the_setting_changes_mid_request(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage083-locked", "secret")
        self.harness.login("stage083-locked", "secret")
        chat = client.post("/api/chats", json={}).json()

        self.harness.web_search.XAI_API_KEY = "test-key"
        fake_duck = FakeDuckDuckGoClient(
            results=[
                DuckDuckGoSearchResult(
                    position=1,
                    title="Duck result",
                    url="https://example.com/duck",
                    snippet="DuckDuckGo response.",
                    page_excerpt="DuckDuckGo page excerpt.",
                )
            ],
            block=True,
        )
        fake_xai = FakeXAIClient(
            results=[
                XAIWebSearchResult(
                    position=1,
                    title="xAI result",
                    url="https://x.ai/news",
                    snippet="xAI response.",
                    page_excerpt="xAI page excerpt.",
                )
            ]
        )
        self.harness.main.app.state.web_search_client = fake_duck
        self.harness.main.app.state.xai_web_search_client = fake_xai

        fake_ollama: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_ollama.response_queue = [[json.dumps({"message": {"content": "answer"}, "done": True})]]

        async def _run_and_switch() -> str:
            task = asyncio.create_task(
                self.harness.run_chat(
                    alice.id,
                    chat["id"],
                    "What is the latest xAI update?",
                    web_search_mode="always",
                )
            )

            await fake_duck.started.wait()
            switch = client.patch("/api/auth/me", json={"web_search_provider": "xai"})
            self.assertEqual(switch.status_code, 200)
            self.assertEqual(switch.json()["web_search_provider"], "xai")

            fake_duck.release.set()
            return await task

        body = asyncio.run(_run_and_switch())

        self.assertEqual(len(fake_duck.calls), 1)
        self.assertEqual(fake_xai.calls, [])
        self.assertIn('"provider":"duckduckgo"', body.replace(" ", ""))

        fake_ollama.response_queue = [[json.dumps({"message": {"content": "answer"}, "done": True})]]
        body_next = asyncio.run(
            self.harness.run_chat(
                alice.id,
                chat["id"],
                "What is the latest xAI update?",
                web_search_mode="always",
            )
        )

        self.assertEqual(len(fake_xai.calls), 1)
        self.assertIn('"provider":"xai"', body_next.replace(" ", ""))

    def test_xai_without_key_rejects_activation_and_keeps_previous_value(self) -> None:
        client = self.harness.client
        assert client is not None

        self.harness.create_user("stage083-missing-key", "secret")
        self.harness.login("stage083-missing-key", "secret")

        me = client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["web_search_provider"], "duckduckgo")
        self.assertNotIn("XAI_API_KEY", me.json())

        response = client.patch("/api/auth/me", json={"web_search_provider": "xai"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(client.get("/api/auth/me").json()["web_search_provider"], "duckduckgo")

        with Session(self.harness.db.engine) as db:
            columns = [row[1] for row in db.exec(text("PRAGMA table_info(users)")).all()]
            self.assertIn("web_search_provider", columns)
            self.assertNotIn("XAI_API_KEY", columns)

    def test_provider_cannot_be_supplied_through_chat_payload(self) -> None:
        client = self.harness.client
        assert client is not None

        self.harness.create_user("stage083-payload", "secret")
        self.harness.login("stage083-payload", "secret")
        chat = client.post("/api/chats", json={}).json()

        response = client.post(
            "/api/chat",
            json={
                "chat_id": chat["id"],
                "content": "Need fresh info",
                "mode": "instant",
                "web_search_mode": "always",
                "web_search_provider": "xai",
            },
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
