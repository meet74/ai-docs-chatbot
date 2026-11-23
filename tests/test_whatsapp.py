import hashlib
import hmac
import json

from docs_chatbot import whatsapp as wa

SECRET = "app-secret"


def sign(body: bytes, secret=SECRET) -> dict:
    return {"X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
            "Content-Type": "application/json"}


def payload(text="How much is a cleaning?", mid="wamid.A1", mtype="text"):
    msg = {"from": "14165550123", "id": mid, "type": mtype}
    if mtype == "text":
        msg["text"] = {"body": text}
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [
        {"field": "messages", "value": {"messaging_product": "whatsapp", "messages": [msg]}}]}]}


def post(client, data, headers=None):
    body = json.dumps(data).encode()
    return client.post("/whatsapp/webhook", content=body, headers=headers if headers is not None else sign(body))


def test_signature_helper():
    body = b'{"a":1}'
    good = sign(body)["X-Hub-Signature-256"]
    assert wa.verify_signature(SECRET, body, good)
    assert not wa.verify_signature(SECRET, body + b" ", good)
    assert not wa.verify_signature(SECRET, body, "sha256=deadbeef")
    assert not wa.verify_signature(SECRET, body, None)
    assert not wa.verify_signature("", body, good)
    assert not wa.verify_signature(SECRET, body, good.replace("sha256=", "sha1="))


def test_verify_handshake(client):
    ok = client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "4711"})
    assert ok.status_code == 200 and ok.text == "4711"
    bad = client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "4711"})
    assert bad.status_code == 403


def test_unsigned_and_badly_signed_posts_are_rejected(client, outbox):
    body = json.dumps(payload()).encode()
    assert client.post("/whatsapp/webhook", content=body).status_code == 403
    assert client.post("/whatsapp/webhook", content=body, headers=sign(body, "wrong")).status_code == 403
    assert not outbox.requests


def test_signed_message_gets_a_reply_through_graph_url(client, outbox):
    assert post(client, payload()).status_code == 200
    sent = outbox.bodies("graph.test")
    assert len(sent) == 1
    req = outbox.to("graph.test")[0]
    assert str(req.url) == "http://graph.test/v21.0/1234567890/messages"
    assert req.headers["authorization"] == "Bearer wa-token"
    assert sent[0]["to"] == "14165550123" and sent[0]["messaging_product"] == "whatsapp"
    assert "$120" in sent[0]["text"]["body"] and "Sources: Services and Prices" in sent[0]["text"]["body"]


def test_duplicate_delivery_is_answered_once(client, outbox):
    post(client, payload(mid="wamid.DUP"))
    post(client, payload(mid="wamid.DUP"))
    assert len(outbox.to("graph.test")) == 1


def test_status_updates_and_non_text_messages(client, outbox):
    status = {"entry": [{"changes": [{"value": {"statuses": [{"id": "x", "status": "delivered"}]}}]}]}
    assert post(client, status).status_code == 200
    assert not outbox.requests
    post(client, payload(mtype="image", mid="wamid.IMG"))
    assert "only read text" in outbox.bodies("graph.test")[0]["text"]["body"]


def test_whatsapp_handoff_names_the_channel(client, outbox):
    post(client, payload(text="I want to speak to a person", mid="wamid.H1"))
    hook = outbox.bodies("hook.test")
    assert hook and hook[0]["channel"] == "whatsapp"


def test_parse_messages_ignores_malformed_bodies():
    assert wa.parse_messages({}) == []
    assert wa.parse_messages({"entry": [{"changes": [{"value": {"messages": [{"type": "text"}]}}]}]}) == []
    msgs = wa.parse_messages(payload())
    assert msgs[0].sender == "14165550123" and msgs[0].text == "How much is a cleaning?"


def test_post_without_app_secret_is_refused(settings):
    import httpx
    from fastapi.testclient import TestClient
    from docs_chatbot.app import create_app

    settings.whatsapp_app_secret = ""
    with TestClient(create_app(settings)) as c:
        assert c.post("/whatsapp/webhook", json=payload()).status_code == 503
