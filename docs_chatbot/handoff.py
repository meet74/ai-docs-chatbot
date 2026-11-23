"""Handoff records (SQLite) and the Slack-compatible webhook notification."""
import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path

import httpx

from .prompt import Turn

log = logging.getLogger("docs_chatbot.handoff")

REASONS = {
    "user_requested": "Customer asked for a person",
    "needs_human": "The assistant could not answer from the documents",
    "low_confidence": "Low confidence answer",
    "model_error": "The assistant had a technical problem",
}


class HandoffStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS handoffs (
                 id TEXT PRIMARY KEY, session_id TEXT, reason TEXT, transcript TEXT,
                 status TEXT, notified INTEGER DEFAULT 0, created_at REAL)""")
        self._conn.commit()

    def create(self, session_id: str, reason: str, transcript: list[Turn]) -> dict:
        rec = {"id": "H-" + uuid.uuid4().hex[:8].upper(), "session_id": session_id,
               "reason": reason, "status": "open", "created_at": time.time(),
               "transcript": [{"role": t.role, "content": t.content} for t in transcript]}
        self._conn.execute(
            "INSERT INTO handoffs (id, session_id, reason, transcript, status, created_at) VALUES (?,?,?,?,?,?)",
            (rec["id"], session_id, reason, json.dumps(rec["transcript"]), "open", rec["created_at"]))
        self._conn.commit()
        return rec

    def mark_notified(self, handoff_id: str) -> None:
        self._conn.execute("UPDATE handoffs SET notified=1 WHERE id=?", (handoff_id,))
        self._conn.commit()

    def get(self, handoff_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, session_id, reason, transcript, status, notified, created_at FROM handoffs WHERE id=?",
            (handoff_id,)).fetchone()
        if not row:
            return None
        return {"id": row[0], "session_id": row[1], "reason": row[2], "transcript": json.loads(row[3]),
                "status": row[4], "notified": bool(row[5]), "created_at": row[6]}

    def purge_older_than(self, days: int = 90) -> int:
        cur = self._conn.execute("DELETE FROM handoffs WHERE created_at < ?", (time.time() - days * 86400,))
        self._conn.commit()
        return cur.rowcount


def build_payload(rec: dict, business: str, fmt: str = "json", channel_label: str = "web") -> dict:
    lines = [f"{'Customer' if t['role'] == 'user' else 'Bot'}: {t['content']}" for t in rec["transcript"]]
    transcript_text = "\n".join(lines) or "(no messages)"
    reason = REASONS.get(rec["reason"], rec["reason"])
    text = f"New handoff {rec['id']} for {business} ({channel_label}): {reason}"
    slack = {
        "text": text,
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": f"Handoff {rec['id']}"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Reason*\n{reason}"},
                {"type": "mrkdwn", "text": f"*Channel*\n{channel_label}"}]},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Transcript*\n```" + transcript_text[:2600] + "```"}},
        ],
    }
    if fmt == "slack":
        return slack
    # The json format is the Slack payload plus structured fields, for n8n or a helpdesk.
    return {**slack, "handoff_id": rec["id"], "reason": rec["reason"], "channel": channel_label,
            "session_id": rec["session_id"], "created_at": int(rec["created_at"]),
            "transcript": rec["transcript"]}


async def notify(url: str, payload: dict, http: httpx.AsyncClient) -> bool:
    if not url:
        return False
    try:
        r = await http.post(url, json=payload, timeout=10)
        return r.status_code < 300
    except httpx.HTTPError as e:
        log.warning("handoff webhook failed: %s", type(e).__name__)
        return False
