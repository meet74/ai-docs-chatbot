"""Input and output checks around the model. The model is not the only line of defence."""
import json
import re

from pydantic import ValidationError

from .prompt import LLMRequest
from .retrieval import Passage
from .schemas import AnswerPayload, Citation

_INJECTION = [
    r"ignore (all |any |the )?(previous|prior|above|earlier|preceding) (instructions|rules|prompts?)",
    r"ignore (the |your )?(documents|passages|sources|context)",
    r"disregard (all |any |the |your )?(previous|prior|above|instructions|rules)",
    r"(reveal|print|show|repeat|output|tell me) (me )?(your |the )?(system|hidden|initial) (prompt|instructions|message)",
    r"you are now (?!going)",
    r"pretend (to be|you are)",
    r"developer mode|jailbreak|\bDAN\b",
]
_INJECTION_RE = re.compile("|".join(_INJECTION), re.I)

_HUMAN = re.compile(
    r"\b(talk|speak|chat|connect|transfer|escalate)\b.{0,25}\b(human|person|someone|agent|representative|"
    r"receptionist|staff|team member|real person)\b|\b(real|live) (person|human|agent)\b|"
    r"\bhuman (agent|please)\b|\bcall me\b", re.I)

_SMALLTALK = re.compile(
    r"^\s*(hi|hello|hey|good (morning|afternoon|evening)|thanks|thank you|thx|ok|okay|bye|goodbye)[\s!.?]*$", re.I)

_MONEY = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")
_PERCENT = re.compile(r"\d+(?:\.\d+)?\s?%")


def looks_like_injection(message: str) -> bool:
    return bool(_INJECTION_RE.search(message))


def asks_for_human(message: str) -> bool:
    return bool(_HUMAN.search(message))


def is_smalltalk(message: str) -> bool:
    return bool(_SMALLTALK.match(message))


def parse_payload(raw: str) -> AnswerPayload:
    """Accept bare JSON or JSON wrapped in a code fence or a sentence; reject everything else."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in reply")
    try:
        return AnswerPayload.model_validate(json.loads(text[start:end + 1]))
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"invalid reply: {type(e).__name__}") from e


def _norm_money(s: str) -> str:
    return re.sub(r"[\s,]", "", s)


def unsupported_figures(answer: str, passages: list[Passage]) -> list[str]:
    """Dollar amounts and percentages in the answer that no passage contains."""
    corpus = " ".join(p.chunk.text for p in passages)
    known_money = {_norm_money(m) for m in _MONEY.findall(corpus)}
    known_pct = {re.sub(r"\s", "", m) for m in _PERCENT.findall(corpus)}
    bad = [m for m in _MONEY.findall(answer) if _norm_money(m) not in known_money]
    bad += [m for m in _PERCENT.findall(answer) if re.sub(r"\s", "", m) not in known_pct]
    return bad


def check_citations(payload: AnswerPayload, passages: list[Passage]) -> list[Citation]:
    """Keep only citations that point at a passage that was actually retrieved."""
    by_doc: dict[str, list[Passage]] = {}
    for p in passages:
        by_doc.setdefault(p.chunk.doc.lower(), []).append(p)
    out: list[Citation] = []
    for c in payload.citations:
        group = by_doc.get(c.doc.strip().lower())
        if not group:
            continue
        match = next((p for p in group if p.chunk.section.lower() == c.section.strip().lower()), group[0])
        cit = Citation(doc=match.chunk.doc, section=match.chunk.section, source=match.chunk.source)
        if cit not in out:
            out.append(cit)
    return out


def sanitize_message(message: str, max_chars: int) -> str:
    message = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", message).strip()
    return message[:max_chars]


async def generate_validated(llm, req: LLMRequest, retries: int = 2) -> AnswerPayload:
    correction = None
    last: Exception | None = None
    for _ in range(retries + 1):
        raw = await llm.complete(req, correction)
        try:
            return parse_payload(raw)
        except ValueError as e:
            last = e
            correction = ("Your last reply was not valid. Reply with only the JSON object "
                          "with keys answer, citations, confidence, needs_human.")
    raise ValueError(str(last))
