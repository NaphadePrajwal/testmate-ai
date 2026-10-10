from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.schemas.common import APIModel


class AnalysisSource(StrEnum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    SUGGESTED = "suggested"
    UNSPECIFIED = "unspecified"


class RequirementType(StrEnum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    BUSINESS_RULE = "business_rule"
    CONSTRAINT = "constraint"
    OTHER = "other"
    UNCERTAIN = "uncertain"


class ClarityLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AnalysisItem(APIModel):
    text: str = Field(min_length=1, max_length=5_000)
    source: AnalysisSource


class RequirementTypeAssessment(APIModel):
    classification: RequirementType
    rationale: AnalysisItem


class QualityAssessment(APIModel):
    clarity: ClarityLevel
    completeness: ClarityLevel
    reasons: list[AnalysisItem] = Field(min_length=1, max_length=20)
    limitation: str = Field(min_length=1, max_length=2_000)


class RequirementAnalysis(APIModel):
    summary: AnalysisItem
    requirement_type: RequirementTypeAssessment
    actors_and_entities: list[AnalysisItem] = Field(max_length=50)
    expected_behaviors: list[AnalysisItem] = Field(min_length=1, max_length=50)
    inputs: list[AnalysisItem] = Field(max_length=50)
    outputs: list[AnalysisItem] = Field(max_length=50)
    preconditions: list[AnalysisItem] = Field(min_length=1, max_length=30)
    postconditions: list[AnalysisItem] = Field(min_length=1, max_length=30)
    acceptance_criteria: list[AnalysisItem] = Field(min_length=1, max_length=50)
    ambiguities_and_missing_information: list[AnalysisItem] = Field(max_length=50)
    dependencies_and_constraints: list[AnalysisItem] = Field(max_length=50)
    clarification_questions: list[AnalysisItem] = Field(max_length=30)
    quality_assessment: QualityAssessment


class AnalysisMetadata(APIModel):
    provider: str
    model: str
    prompt_version: str
    analyzed_at: datetime


class RequirementAnalysisRead(APIModel):
    analysis: RequirementAnalysis
    metadata: AnalysisMetadata
