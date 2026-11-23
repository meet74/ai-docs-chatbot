import logging

from docs_chatbot.privacy import redact
from docs_chatbot.ratelimit import RateLimiter

from .test_chat import chat


def test_sliding_window():
    rl = RateLimiter(3, window=10)
    assert [rl.check("k", now=t)[0] for t in (0, 1, 2)] == [True, True, True]
    ok, wait = rl.check("k", now=3)
    assert not ok and 1 <= wait <= 10
    assert rl.check("other", now=3)[0]
    assert rl.check("k", now=10.5)[0]


def test_chat_endpoint_returns_429_with_retry_after(settings, outbox):
    import httpx
    from fastapi.testclient import TestClient
    from docs_chatbot.app import create_app

    settings.rate_limit_session_per_minute = 3
    http = httpx.AsyncClient(transport=httpx.MockTransport(outbox.handler))
    with TestClient(create_app(settings, http=http)) as c:
        codes = [c.post("/chat", json={"message": "hours?", "session_id": "rate-limit-1"}).status_code for _ in range(5)]
        other = c.post("/chat", json={"message": "hours?", "session_id": "rate-limit-2"}).status_code
        blocked = c.post("/chat", json={"message": "hours?", "session_id": "rate-limit-1"})
    assert codes == [200, 200, 200, 429, 429] and other == 200
    assert int(blocked.headers["retry-after"]) >= 1


def test_ip_limit_applies_across_sessions(settings):
    from fastapi.testclient import TestClient
    from docs_chatbot.app import create_app

    settings.rate_limit_ip_per_minute = 2
    with TestClient(create_app(settings)) as c:
        codes = [c.post("/chat", json={"message": "hours?", "session_id": f"ip-limit-{i:02d}"}).status_code for i in range(4)]
    assert codes == [200, 200, 429, 429]


def test_redact():
    text = "mail me at jo.doe@example.com or call (416) 555-0142, card 4111 1111 1111 1111"
    out = redact(text)
    assert "example.com" not in out and "555-0142" not in out and "4111" not in out


def test_message_content_never_reaches_logs(client, caplog):
    with caplog.at_level(logging.DEBUG):
        chat(client, "My email is secret.person@example.com and my number is 416-555-0188, how much is a cleaning?",
             sid="pii-test-0001")
        chat(client, "talk to a human, I am secret.person@example.com", sid="pii-test-0001")
    assert "secret.person" not in caplog.text and "555-0188" not in caplog.text
    assert "cleaning" not in caplog.text
    assert "chat session=" in caplog.text


def test_ingest_requires_token_and_rejects_bad_types(settings, tmp_path):
    import shutil
    from fastapi.testclient import TestClient
    from docs_chatbot.app import create_app

    kb = tmp_path / "kb"
    shutil.copytree(settings.kb_dir, kb)
    settings.kb_dir = kb
    with TestClient(create_app(settings)) as client:
        _ingest_checks(client, kb)


def _ingest_checks(client, kb):
    assert client.post("/ingest").status_code == 401
    h = {"X-Admin-Token": "admin-secret"}
    bad = client.post("/ingest", headers=h, files={"files": ("evil.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 400
    traversal = client.post("/ingest", headers=h, files={"files": ("../../x.md", b"# x\n\nhello", "text/markdown")})
    assert traversal.status_code == 200 and traversal.json()["saved"] == ["x.md"]
    assert (kb / "x.md").exists() and traversal.json()["documents"] == 10
    found = client.post("/chat", json={"message": "hello hours", "session_id": "ingest-test-1"})
    assert found.status_code == 200
