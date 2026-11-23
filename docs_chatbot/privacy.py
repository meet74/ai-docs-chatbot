"""PII redaction for anything that reaches a log line."""
import hashlib
import logging
import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d{1,2}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
_OHIP = re.compile(r"\b\d{4}[ -]?\d{3}[ -]?\d{3}\b")


def redact(text: str) -> str:
    text = _EMAIL.sub("[email]", text)
    text = _CARD.sub("[number]", text)
    text = _PHONE.sub("[phone]", text)
    return _OHIP.sub("[number]", text)


def pseudonym(value: str) -> str:
    """Stable short id for logs, so one session can be followed without exposing a phone number."""
    return hashlib.sha256(value.encode()).hexdigest()[:10]


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True
