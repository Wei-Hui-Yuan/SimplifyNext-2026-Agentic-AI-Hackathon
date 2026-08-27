"""
Pydantic schemas for structured-output model calls — the
04a_planning_decomposition.py pattern (`chat_model().with_structured_output(Model)`),
never manual JSON-text parsing.
"""

from pydantic import BaseModel, Field


class TrajectoryPath(BaseModel):
    name: str = Field(description="Short label, e.g. 'AI Research', 'AI Industry', 'AI + Entrepreneurship'")
    rationale: str = Field(description="Why this path fits the student's stated goal, one or two sentences")
    steps: list[str] = Field(description="4-7 concrete steps in rough order: modules, RA/internship, projects")
    likely_outcomes: list[str] = Field(description="2-3 short phrases describing where this path tends to lead")


class TrajectorySet(BaseModel):
    paths: list[TrajectoryPath] = Field(description="2-3 distinct trajectory paths, not more")


class LeverageMove(BaseModel):
    title: str
    move_type: str = Field(description="one of: module | meeting | apply | skip | event")
    why: str = Field(description="one sentence, specific to this student's profile")
    deadline: str | None = None
    confidence_note: str | None = Field(
        default=None, description="e.g. 'high — you've completed the prerequisite modules'"
    )
    ref_id: str | None = Field(default=None, description="id of the underlying candidate record, if any")


class LeverageList(BaseModel):
    moves: list[LeverageMove] = Field(description="Exactly 5 moves, ranked highest-leverage first")


class OutreachDraft(BaseModel):
    subject: str
    body: str
