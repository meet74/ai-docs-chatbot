from pydantic import BaseModel, Field, field_validator


class Citation(BaseModel):
    doc: str
    section: str = ""
    source: str = ""


class AnswerPayload(BaseModel):
    """What the model must return. Parsed strictly; anything else is retried."""
    answer: str = Field(min_length=1, max_length=2000)
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_human: bool = False

    @field_validator("answer")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")
    request_human: bool = False


class HandoffInfo(BaseModel):
    id: str
    status: str            # "created" or "already_open"
    notified: bool


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[Citation]
    confidence: float
    needs_human: bool
    refused: bool = False
    reason: str = ""
    handoff: HandoffInfo | None = None
