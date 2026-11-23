"""The chat flow: guard, retrieve, answer, validate, decide on handoff."""
import logging
import time

import httpx

from . import guardrails as g
from .config import Settings
from .handoff import HandoffStore, build_payload, notify
from .llm import REFUSAL_TEXT, LLMClient, LLMError
from .memory import SessionStore
from .privacy import pseudonym
from .prompt import LLMRequest
from .retrieval import Passage, Retriever
from .schemas import ChatResponse, Citation, HandoffInfo

log = logging.getLogger("docs_chatbot.chat")

OFF_TOPIC = "I can only help with questions about {business}. Is there something about our services, hours or policies I can look up for you?"
HANDOFF_NOTE = "I have passed this conversation to our team. Someone will follow up during opening hours."
ALREADY_NOTE = "Our team already has this conversation and will follow up."
INJECTION_REPLY = "I can only answer questions using our published documents, so I can't do that."
GREETING = "Hello! Ask me about services, prices, hours, booking or insurance and I will answer from our documents."


class ChatService:
    def __init__(self, settings: Settings, retriever: Retriever, llm: LLMClient,
                 sessions: SessionStore, handoffs: HandoffStore, http: httpx.AsyncClient):
        self.s, self.retriever, self.llm = settings, retriever, llm
        self.sessions, self.handoffs, self.http = sessions, handoffs, http

    async def handle(self, session_id: str, message: str, request_human: bool = False,
                     channel: str = "web") -> ChatResponse:
        t0 = time.perf_counter()
        message = g.sanitize_message(message, self.s.max_message_chars)
        resp = await self._answer(session_id, message, request_human, channel)
        # Content of the conversation is never logged, only the outcome.
        log.info("chat session=%s channel=%s reason=%s refused=%s handoff=%s ms=%d",
                 pseudonym(session_id), channel, resp.reason or "answered", resp.refused,
                 resp.handoff.status if resp.handoff else "-", (time.perf_counter() - t0) * 1000)
        return resp

    async def _answer(self, sid: str, message: str, request_human: bool, channel: str) -> ChatResponse:
        s = self.s
        if request_human or g.asks_for_human(message):
            return await self._escalate(sid, message, "user_requested", channel,
                                        "Of course. " + HANDOFF_NOTE, reason="user_requested")
        if g.is_smalltalk(message):
            return self._plain(sid, message, GREETING, "smalltalk")
        if g.looks_like_injection(message):
            return self._plain(sid, message, INJECTION_REPLY, "injection", refused=True)

        passages = await self.retriever.search(self._query(sid, message), s.top_k)
        best = max((p.coverage for p in passages), default=0.0)
        if best < s.scope_floor:
            return self._plain(sid, message, OFF_TOPIC.format(business=s.business_name),
                               "out_of_scope", refused=True)

        req = LLMRequest(question=message, passages=passages, history=self.sessions.history(sid),
                         business=s.business_name)
        try:
            payload = await g.generate_validated(self.llm, req)
        except (LLMError, ValueError):
            return await self._escalate(
                sid, message, "model_error", channel,
                "Sorry, I had a problem answering that. " + HANDOFF_NOTE, reason="model_error")

        citations = g.check_citations(payload, passages)
        refuse = False
        reason = ""
        if payload.needs_human or payload.confidence < 0.3:
            refuse, reason = True, "needs_human"
        elif not citations:
            refuse, reason = True, "no_valid_citation"
        elif g.unsupported_figures(payload.answer, passages):
            refuse, reason = True, "unsupported_figure"
        elif payload.confidence < s.confidence_threshold:
            reason = "low_confidence"

        if refuse:
            return await self._escalate(
                sid, message, "needs_human", channel,
                f"{REFUSAL_TEXT} {HANDOFF_NOTE}", reason=reason, refused=True)

        answer = payload.answer
        if reason == "low_confidence":
            return await self._escalate(
                sid, message, "low_confidence", channel,
                f"{answer}\n\nI am not fully sure about this. {HANDOFF_NOTE}",
                reason=reason, citations=citations, confidence=payload.confidence)

        self.sessions.add_exchange(sid, message, answer)
        return ChatResponse(session_id=sid, answer=answer, citations=citations,
                            confidence=payload.confidence, needs_human=False)

    def _query(self, sid: str, message: str) -> str:
        """Short follow-ups ("and on Saturdays?") borrow the previous question for retrieval."""
        history = self.sessions.history(sid)
        if len(message.split()) < 5 and history:
            prev = next((t.content for t in reversed(history) if t.role == "user"), "")
            return f"{prev} {message}"
        return message

    def _plain(self, sid: str, message: str, answer: str, reason: str, refused: bool = False) -> ChatResponse:
        self.sessions.add_exchange(sid, message, answer)
        return ChatResponse(session_id=sid, answer=answer, citations=[], confidence=0.0 if refused else 1.0,
                            needs_human=False, refused=refused, reason=reason)

    async def _escalate(self, sid: str, message: str, handoff_reason: str, channel: str, answer: str,
                        reason: str, refused: bool = False, citations: list[Citation] | None = None,
                        confidence: float = 0.0) -> ChatResponse:
        sess = self.sessions.get(sid)
        self.sessions.add_exchange(sid, message, answer)
        now = time.time()
        if sess.handoff_id and now - sess.handoff_at < self.s.handoff_cooldown_seconds:
            info = HandoffInfo(id=sess.handoff_id, status="already_open", notified=True)
            answer = answer.replace(HANDOFF_NOTE, ALREADY_NOTE)
        else:
            rec = self.handoffs.create(sid, handoff_reason, self.sessions.history(sid))
            payload = build_payload(rec, self.s.business_name, self.s.handoff_webhook_format, channel)
            ok = await notify(self.s.handoff_webhook_url, payload, self.http)
            if ok:
                self.handoffs.mark_notified(rec["id"])
            sess.handoff_id, sess.handoff_at = rec["id"], now
            info = HandoffInfo(id=rec["id"], status="created", notified=ok)
        return ChatResponse(session_id=sid, answer=answer, citations=citations or [], confidence=confidence,
                            needs_human=True, refused=refused, reason=reason, handoff=info)
