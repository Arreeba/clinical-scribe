from typing import Literal
from pydantic import BaseModel, Field


class TranscriptLine(BaseModel):
    id: int                                  # line number, starts at 1
    speaker: Literal["doctor", "patient"]
    text: str


class Statement(BaseModel):
    text: str                                # one fact, stated plainly
    source_lines: list[int] = Field(default_factory=list)  # transcript line ids
    needs_review: bool = False               # True for medicines, doses, odd words
    review_reason: str = ""                  # short reason when needs_review is True


class Note(BaseModel):
    complaint: list[Statement] = Field(default_factory=list)
    history: list[Statement] = Field(default_factory=list)
    assessment: list[Statement] = Field(default_factory=list)
    plan: list[Statement] = Field(default_factory=list)


# Consultation states and the moves allowed between them
STATES = ("draft", "edited", "approved")

ALLOWED_TRANSITIONS = {
    "draft": {"edited", "approved"},
    "edited": {"edited", "approved"},
    "approved": set(),   # locked: nothing allowed after approval
}


def can_move(current: str, new: str) -> bool:
    return new in ALLOWED_TRANSITIONS.get(current, set())