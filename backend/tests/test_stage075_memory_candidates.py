from __future__ import annotations

import asyncio
import json
import sys
import unittest
from unittest import mock
from pathlib import Path

from sqlmodel import Session, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "stage075.sqlite3"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.test_stage06 import BackendHarness, FakeOllamaClient
from app.services.memory_candidates import update_memory_candidate


class Stage075MemoryCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = DB_PATH
        if self.db_path.exists():
            self.db_path.unlink()
        self.harness = BackendHarness(self.db_path)

    def tearDown(self) -> None:
        self.harness.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_analyze_accept_and_reject_memory_candidates(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage075-alice", "secret")
        self.harness.login("stage075-alice", "secret")
        chat = client.post("/api/chats", json={}).json()

        fake_client: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_client.response_queue = [
            [
                json.dumps(
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "candidates": [
                                        {"content": "Prefers short answers."},
                                        {"content": "Drinks tea without sugar."},
                                    ]
                                }
                            )
                        },
                        "done": True,
                    }
                )
            ]
        ]

        analyzed = client.post(f"/api/chats/{chat['id']}/memory-candidates/analyze")
        self.assertEqual(analyzed.status_code, 200)
        self.assertEqual(len(analyzed.json()), 2)
        self.assertTrue(all(item["status"] == "pending" for item in analyzed.json()))

        candidate_id = analyzed.json()[0]["id"]
        with Session(self.harness.db.engine) as db:
            candidate = db.get(self.harness.memory.MemoryCandidate, candidate_id)
            assert candidate is not None
            with mock.patch.object(db, "commit", wraps=db.commit) as commit_mock:
                updated, created_memory = update_memory_candidate(
                    db,
                    candidate,
                    status="accepted",
                )
                self.assertEqual(commit_mock.call_count, 1)
            self.assertIsNotNone(created_memory)
            self.assertEqual(updated.status, "accepted")

        with Session(self.harness.db.engine) as db:
            memories_count = db.exec(select(self.harness.memory.MemoryItem)).all()
            self.assertEqual(len(memories_count), 1)
            candidate = db.get(self.harness.memory.MemoryCandidate, candidate_id)
            assert candidate is not None
            updated, created_memory = update_memory_candidate(
                db,
                candidate,
                status="accepted",
            )
            self.assertIsNone(created_memory)
            self.assertEqual(updated.status, "accepted")

        accepted = client.patch(
            f"/api/chats/{chat['id']}/memory-candidates/{candidate_id}",
            json={"status": "accepted"},
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["status"], "accepted")

        memories = client.get("/api/memories").json()
        self.assertIn(accepted.json()["content"], [item["content"] for item in memories])

        remaining = client.get(f"/api/chats/{chat['id']}/memory-candidates").json()
        self.assertTrue(all(item["status"] == "pending" for item in remaining))
        self.assertNotIn(accepted.json()["content"], [item["content"] for item in remaining])

        rejected_id = next(
            item["id"] for item in remaining if item["content"] != accepted.json()["content"]
        )
        rejected = client.patch(
            f"/api/chats/{chat['id']}/memory-candidates/{rejected_id}",
            json={"status": "rejected"},
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["status"], "rejected")

    def test_analyze_is_blocked_during_active_generation(self) -> None:
        client = self.harness.client
        assert client is not None

        self.harness.create_user("stage075-blocked", "secret")
        self.harness.login("stage075-blocked", "secret")
        chat = client.post("/api/chats", json={}).json()

        self.harness.main.app.state.active_chat_generations.add(chat["id"])
        try:
            response = client.post(f"/api/chats/{chat['id']}/memory-candidates/analyze")
        finally:
            self.harness.main.app.state.active_chat_generations.discard(chat["id"])

        self.assertEqual(response.status_code, 409)

    def test_memory_candidate_routes_are_chat_scoped(self) -> None:
        client = self.harness.client
        assert client is not None

        alice = self.harness.create_user("stage075-owner", "secret")
        bob = self.harness.create_user("stage075-bob", "secret")
        self.harness.login("stage075-owner", "secret")

        alice_chat = client.post("/api/chats", json={}).json()
        bob_chat = self.harness.insert_chat(bob.id, "Bob chat")

        fake_client: FakeOllamaClient = self.harness.main.app.state.ollama_client
        fake_client.response_queue = [
            [
                json.dumps(
                    {
                        "message": {
                            "content": json.dumps({"candidates": [{"content": "Alice fact."}]})
                        },
                        "done": True,
                    }
                )
            ]
        ]

        client.post(f"/api/chats/{alice_chat['id']}/memory-candidates/analyze")

        self.assertEqual(client.get(f"/api/chats/{bob_chat.id}/memory-candidates").status_code, 404)
        self.assertEqual(
            client.patch(
                f"/api/chats/{bob_chat.id}/memory-candidates/1",
                json={"status": "accepted"},
            ).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
