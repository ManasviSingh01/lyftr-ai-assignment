import importlib
import os

os.environ.setdefault("LLM_API_KEYS", "fake-key-1,fake-key-2")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("ENABLE_FAILURE_SIMULATION", "true")

from fastapi.testclient import TestClient
from app import main

client = TestClient(main.app)


def test_health():
    with client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["keys_configured"] == 2


def test_validation_blank_message():
    with client:
        r = client.post("/chat", json={"session_id": "s1", "message": "   "})
        assert r.status_code == 422


def test_unknown_session():
    with client:
        r = client.get("/sessions/no-such-session/messages")
        assert r.status_code == 404
        assert r.json() == {"detail": "session not found"}


def test_all_simulated_failures_are_503_and_not_stored():
    with client:
        r = client.post("/chat", headers={"X-Simulate-Failure": "*=429"}, json={"session_id": "sim-all", "message": "hello"})
        assert r.status_code == 503
        assert r.json() == {"detail": "all providers unavailable"}
        history = client.get("/sessions/sim-all/messages")
        assert history.status_code == 404
