"""Pydantic schemas passed between agents. Every agent hand-off is validated
against one of these models so a malformed LLM response fails loudly here
instead of silently corrupting a downstream agent."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class ClauseType(str, Enum):
    TERMINATION = "termination"
    LIABILITY = "liability"
    PAYMENT_TERMS = "payment_terms"
    CONFIDENTIALITY = "confidentiality"
    INDEMNITY = "indemnity"
    AUTO_RENEWAL = "auto_renewal"
    GOVERNING_LAW = "governing_law"
    OTHER = "other"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskVerdict(str, Enum):
    LOW_RISK = "low_risk"
    MODERATE_RISK = "moderate_risk"
    HIGH_RISK = "high_risk"


class Clause(BaseModel):
    id: str
    type: ClauseType
    text: str
    confidence: float = Field(ge=0, le=1, default=1.0)


class ExtractionResult(BaseModel):
    clauses: list[Clause]


class Rule(BaseModel):
    id: str
    name: str
    applies_to: ClauseType
    description: str
    severity: Severity


class RiskFinding(BaseModel):
    clause_id: str
    rule_id: str
    rule_name: str
    severity: Severity
    explanation: str


class RiskAnalysisResult(BaseModel):
    findings: list[RiskFinding]


class ExecutiveSummary(BaseModel):
    verdict: RiskVerdict
    summary: str
    key_points: list[str]


# Raw LLM outputs, before an agent fills in what code can derive itself. Output tokens are nearly
# all of a review's wall time, so the model is asked only for what it alone can judge.
class _Row(BaseModel):
    """Also accepts a compact JSON row in field order, e.g. ["liability", 5, 0.9]:
    rows cost about half the output tokens of {"type": ..., "start": ...} objects."""

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, value):
        if isinstance(value, (list, tuple)):
            return dict(zip(cls.model_fields, value))
        return value


class ClauseSpan(_Row):
    type: ClauseType
    start: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1, default=1.0)


class ClauseSpans(BaseModel):
    clauses: list[ClauseSpan]


class RiskCheck(_Row):
    index: int = Field(ge=1)
    violates: bool
    reason: str = ""


class RiskChecks(BaseModel):
    checks: list[RiskCheck]


class SummaryDraft(BaseModel):
    summary: str
    key_points: list[str]


class ReviewReport(BaseModel):
    document_name: str
    created_at: datetime
    clauses: list[Clause]
    findings: list[RiskFinding]
    executive_summary: ExecutiveSummary


class ReviewStatus(str, Enum):
    """Mirrors the pipeline stages in agents/graph.py, plus the two terminal states."""

    EXTRACTING = "extracting"
    ANALYZING = "analyzing"
    SUMMARIZING = "summarizing"
    DONE = "done"
    FAILED = "failed"


class ReviewRecord(BaseModel):
    """What GET /reviews/{id} returns -- a review at any point in its lifecycle.
    `report` is populated once `status` reaches DONE; `error` once it reaches FAILED."""

    id: int
    document_name: str
    created_at: datetime
    status: ReviewStatus
    error: str | None = None
    report: ReviewReport | None = None
