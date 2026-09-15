"""Pydantic schemas passed between agents. Every agent hand-off is validated
against one of these models so a malformed LLM response fails loudly here
instead of silently corrupting a downstream agent."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


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


class ReviewReport(BaseModel):
    document_name: str
    created_at: datetime
    clauses: list[Clause]
    findings: list[RiskFinding]
    executive_summary: ExecutiveSummary
