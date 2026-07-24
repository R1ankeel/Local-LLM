from __future__ import annotations

import asyncio
import json
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "stage082_web_search_policy.sqlite3"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.clients.duckduckgo import DuckDuckGoSearchResult
from app.models.chat import ChatTurnRequest
from app.services.web_search_policy import decide_web_search
from tests.test_stage06 import BackendHarness, FakeOllamaClient


@dataclass
class FakeDuckDuckGoClient:
    results: list[DuckDuckGoSearchResult]

    def __post_init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def aclose(self) -> None:
        return None

    async def search(self, query: str, max_results: int = 5) -> list[DuckDuckGoSearchResult]:
        self.calls.append({"query": query, "max_results": max_results})
        return self.results[:max_results]


class Stage082WebSearchPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = DB_PATH
        if self.db_path.exists():
            self.db_path.unlink()
        self.harness = BackendHarness(self.db_path)

    def tearDown(self) -> None:
        self.harness.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_policy_decision_prefers_explicit_modes_and_detects_signals(self) -> None:
        off_payload = ChatTurnRequest(chat_id=1, content="search the web", web_search_mode="off")
        off_decision = decide_web_search(off_payload)
        self.assertFalse(off_decision.should_search)
        self.assertEqual(off_decision.reason_code, "mode_off")

        auto_payload = ChatTurnRequest(
            chat_id=1,
            content="What's the latest news about OpenAI?",
            web_search_mode="auto",
        )
        auto_decision = decide_web_search(auto_payload)
        self.assertTrue(auto_decision.should_search)
        self.assertEqual(auto_decision.reason_code, "current_information")

        url_payload = ChatTurnRequest(
            chat_id=1,
            content="Please summarize https://example.com/article",
            web_search_mode="auto",
        )
        url_decision = decide_web_search(url_payload)
        self.assertTrue(url_decision.should_search)
        self.assertEqual(url_decision.reason_code, "url_lookup")

        always_payload = ChatTurnRequest(chat_id=1, content="Hello there", web_search_mode="always")
        always_decision = decide_web_search(always_payload)
        self.assertTrue(always_decision.should_search)
        self.assertEqual(always_decision.reason_code, "mode_always")

        legacy_payload = ChatTurnRequest(chat_id=1, content="Hello there", use_web_search=True)
        legacy_decision = decide_web_search(legacy_payload)
        self.assertTrue(legacy_decision.should_search)
        self.assertEqual(legacy_decision.reason_code, "forced_on")

    def test_auto_mode_skips_plain_questions_and_searches_for_urls(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage082-auto", "secret")
        self.harness.login("stage082-auto", "secret")
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
        fake_ollama.response_queue = [[json.dumps({"message": {"content": "ok"}, "done": True})]]

        asyncio.run(
            self.harness.run_chat(
                alice.id,
                chat["id"],
                "How are you?",
                web_search_mode="auto",
            )
        )
        self.assertEqual(fake_search.calls, [])

        fake_ollama.response_queue = [[json.dumps({"message": {"content": "ok"}, "done": True})]]
        asyncio.run(
            self.harness.run_chat(
                alice.id,
                chat["id"],
                "Summarize https://example.com/openai",
                web_search_mode="auto",
            )
        )

        self.assertEqual(len(fake_search.calls), 1)
        self.assertEqual(fake_search.calls[0]["query"], "Summarize https://example.com/openai")
        request = fake_ollama.captured_requests[-1]
        self.assertIn("Web search results", request["messages"][0]["content"])

    def test_always_forces_search_even_without_signals(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage082-always", "secret")
        self.harness.login("stage082-always", "secret")
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

        asyncio.run(
            self.harness.run_chat(
                alice.id,
                chat["id"],
                "Hello there",
                web_search_mode="always",
            )
        )

        self.assertEqual(len(fake_search.calls), 1)
        self.assertEqual(fake_search.calls[0]["query"], "Hello there")


if __name__ == "__main__":
    unittest.main()
