"""WhatsApp Cloud API: signature check, payload parsing, and sending replies."""
import hashlib
import hmac
import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger("docs_chatbot.whatsapp")


@dataclass
class Incoming:
    id: str
    sender: str
    type: str
    text: str


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


def parse_messages(payload: dict) -> list[Incoming]:
    """Pull user messages out of a webhook body. Status updates and unknown shapes yield nothing."""
    out: list[Incoming] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for m in value.get("messages") or []:
                mtype = m.get("type", "")
                text = (m.get("text") or {}).get("body", "") if mtype == "text" else ""
                if m.get("id") and m.get("from"):
                    out.append(Incoming(id=m["id"], sender=m["from"], type=mtype, text=text))
    return out


def format_reply(answer: str, citations: list) -> str:
    if not citations:
        return answer
    src = "; ".join(f"{c.doc} ({c.section})" if c.section else c.doc for c in citations)
    return f"{answer}\n\nSources: {src}"


async def send_text(http: httpx.AsyncClient, base_url: str, phone_number_id: str,
                    token: str, to: str, body: str) -> bool:
    url = f"{base_url.rstrip('/')}/{phone_number_id}/messages"
    try:
        r = await http.post(
            url, headers={"Authorization": f"Bearer {token}"}, timeout=15,
            json={"messaging_product": "whatsapp", "to": to, "type": "text",
                  "text": {"preview_url": False, "body": body[:4000]}})
        if r.status_code >= 300:
            log.warning("graph api returned %s", r.status_code)
        return r.status_code < 300
    except httpx.HTTPError as e:
        log.warning("graph api call failed: %s", type(e).__name__)
        return False
