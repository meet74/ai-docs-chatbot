from docs_chatbot.handoff import HandoffStore, build_payload
from docs_chatbot.prompt import Turn

from .test_chat import chat


def test_user_request_creates_record_and_webhook_with_transcript(client, outbox):
    chat(client, "How much is a cleaning?", sid="handoff-0001")
    r = chat(client, "Can I talk to a real person please?", sid="handoff-0001")
    assert r["needs_human"] and r["handoff"]["status"] == "created"
    hook = outbox.bodies("hook.test")
    assert len(hook) == 1
    body = hook[0]
    assert body["text"].startswith("New handoff") and body["blocks"]
    roles = [t["role"] for t in body["transcript"]]
    assert roles[:2] == ["user", "assistant"] and "How much is a cleaning?" in body["transcript"][0]["content"]
    rec = client.app.state.chat.handoffs.get(r["handoff"]["id"])
    assert rec["notified"] and rec["reason"] == "user_requested"


def test_button_flag_triggers_handoff(client):
    r = chat(client, "I would like to talk to a person.", sid="handoff-0002", request_human=True)
    assert r["handoff"]["status"] == "created"


def test_second_request_reuses_open_handoff(client, outbox):
    a = chat(client, "talk to a human", sid="handoff-0003")
    b = chat(client, "please connect me to a person", sid="handoff-0003")
    assert b["handoff"]["status"] == "already_open" and b["handoff"]["id"] == a["handoff"]["id"]
    assert len(outbox.to("hook.test")) == 1


def test_webhook_failure_still_saves_record(settings):
    import httpx
    from fastapi.testclient import TestClient
    from docs_chatbot.app import create_app

    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with TestClient(create_app(settings, http=http)) as c:
        r = chat(c, "talk to a human", sid="handoff-0004")
        assert r["handoff"]["status"] == "created" and r["handoff"]["notified"] is False
        assert c.app.state.chat.handoffs.get(r["handoff"]["id"]) is not None


def test_slack_format_has_only_slack_keys(tmp_path):
    store = HandoffStore(tmp_path / "x.db")
    rec = store.create("s1", "needs_human", [Turn("user", "hello"), Turn("assistant", "hi")])
    payload = build_payload(rec, "Maple Grove Dental", "slack", "web")
    assert set(payload) == {"text", "blocks"}
    assert "hello" in payload["blocks"][2]["text"]["text"]


def test_purge_removes_old_records(tmp_path):
    store = HandoffStore(tmp_path / "x.db")
    rec = store.create("s1", "needs_human", [])
    store._conn.execute("UPDATE handoffs SET created_at = 0")
    assert store.purge_older_than(90) == 1 and store.get(rec["id"]) is None
