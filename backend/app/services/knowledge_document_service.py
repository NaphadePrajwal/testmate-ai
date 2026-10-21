import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.defect import Defect
from app.models.enums import DefectStatus, VerificationStatus
from app.models.execution_failure_analysis import ExecutionFailureAnalysis
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.schemas.knowledge import KnowledgeRecordType, PreparedKnowledgeDocument

logger = logging.getLogger(__name__)


def _clean_str(value: Any) -> str:
    """Normalize string input by stripping whitespace and neutralizing control anomalies."""
    if value is None:
        return ""
    return str(value).strip()


class KnowledgeDocumentService:
    """
    Converts PostgreSQL defects, failure analyses, and test cases into normalized,
    serializable PreparedKnowledgeDocuments suitable for embedding and vector indexing.
    """

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    @staticmethod
    def resolve_project_id(record: Any, fallback_project_id: UUID | str | None = None) -> str:
        """
        Authoritatively determine the project ID for an entity.
        Precedence:
        1. Explicit fallback_project_id parameter.
        2. Direct project_id attribute (e.g. ExecutionFailureAnalysis).
        3. Traversal via requirement (e.g. TestCase).
        4. Traversal via execution -> test_case -> requirement (e.g. Defect).
        """
        if fallback_project_id is not None:
            return str(fallback_project_id)

        # Direct attribute
        if hasattr(record, "project_id") and record.project_id is not None:
            return str(record.project_id)

        # TestCase -> Requirement
        if hasattr(record, "requirement") and record.requirement is not None:
            if hasattr(record.requirement, "project_id") and record.requirement.project_id is not None:
                return str(record.requirement.project_id)

        # Defect -> TestExecution -> TestCase -> Requirement
        if hasattr(record, "execution") and record.execution is not None:
            exec_obj = record.execution
            if hasattr(exec_obj, "test_case") and exec_obj.test_case is not None:
                tc = exec_obj.test_case
                if hasattr(tc, "requirement") and tc.requirement is not None:
                    return str(tc.requirement.project_id)

        raise ValueError(
            f"Cannot resolve authoritative project_id for {type(record).__name__} (id={getattr(record, 'id', None)}). "
            "Pass project_id explicitly or ensure parent relationships are loaded."
        )

    def prepare_defect(
        self,
        defect: Defect,
        project_id: UUID | str | None = None,
    ) -> PreparedKnowledgeDocument:
        """
        Prepare a Defect record into a searchable document.
        Distinguishes between verified technical fixes, resolved but unverified defects,
        and unresolved active defects. Never fabricates resolution claims.
        """
        if not getattr(defect, "id", None) or not getattr(defect, "title", None):
            raise ValueError("Defect must have an id and title to be prepared.")

        resolved_project_id = self.resolve_project_id(defect, project_id)

        # Resolution verification lifecycle determination
        raw_v_status = getattr(defect, "verification_status", None)
        verification_status = raw_v_status if raw_v_status is not None else VerificationStatus.UNVERIFIED
        v_status_str = verification_status.value if hasattr(verification_status, "value") else str(verification_status)
        is_verified = (
            v_status_str == VerificationStatus.VERIFIED.value
            and bool(getattr(defect, "resolution_notes", None))
        )
        is_resolved_status = defect.status in (DefectStatus.RESOLVED, DefectStatus.CLOSED)

        # Build clean, structured search text
        lines: list[str] = [
            f"Defect Title: {_clean_str(defect.title)}",
            f"Severity: {defect.severity.value.upper()} | Current Status: {defect.status.value.upper()}",
            f"Verification Status: {v_status_str.upper()}",
            "",
            "Description:",
            _clean_str(defect.description),
        ]

        # Attach related execution / test case context if loaded
        if hasattr(defect, "execution") and defect.execution is not None:
            if defect.execution.error_message:
                lines.extend([
                    "",
                    "Observed Execution Error:",
                    _clean_str(defect.execution.error_message),
                ])
            if hasattr(defect.execution, "test_case") and defect.execution.test_case is not None:
                lines.extend([
                    "",
                    f"Failing Test Case: {_clean_str(defect.execution.test_case.title)}",
                ])

        # Explicit resolution state
        lines.append("")
        if is_verified:
            lines.extend([
                "Resolution Status: VERIFIED TECHNICAL FIX.",
                f"Verified Technical Resolution: {_clean_str(defect.resolution_notes)}",
                f"Verification Method: {_clean_str(getattr(defect, 'verification_method', None) or 'explicit_verification')}",
            ])
            if getattr(defect, "verification_evidence", None):
                lines.append(f"Verification Evidence: {_clean_str(defect.verification_evidence)}")
            if getattr(defect, "verified_at", None):
                lines.append(f"Verified At: {defect.verified_at.isoformat()}")
        elif is_resolved_status:
            lines.extend([
                "Resolution Status: Defect is marked as RESOLVED in defect tracker. "
                "(Note: No verified post-mortem root-cause documentation recorded).",
            ])
            if getattr(defect, "resolution_notes", None):
                lines.append(f"Unverified Resolution Notes: {_clean_str(defect.resolution_notes)}")
        else:
            lines.append(f"Resolution Status: Unresolved active defect ({defect.status.value.upper()}).")

        search_text = "\n".join(lines)

        metadata: dict[str, Any] = {
            "record_type": KnowledgeRecordType.DEFECT.value,
            "source_id": str(defect.id),
            "project_id": resolved_project_id,
            "execution_id": str(defect.execution_id),
            "severity": defect.severity.value,
            "status": defect.status.value,
            "fingerprint": defect.fingerprint,
            "is_verified_resolution": is_verified,
            "has_verified_root_cause": is_verified,
            "verification_status": v_status_str,
            "resolution_notes": getattr(defect, "resolution_notes", None),
            "verification_method": getattr(defect, "verification_method", None),
            "verification_evidence": getattr(defect, "verification_evidence", None),
            "verified_at": defect.verified_at.isoformat() if getattr(defect, "verified_at", None) else None,
            "created_at": defect.created_at.isoformat() if defect.created_at else None,
        }

        return PreparedKnowledgeDocument(
            record_type=KnowledgeRecordType.DEFECT,
            source_id=str(defect.id),
            project_id=resolved_project_id,
            title=defect.title,
            search_text=search_text,
            is_verified_resolution=is_verified,
            metadata=metadata,
            created_at=defect.created_at,
        )

    def prepare_failure_analysis(
        self,
        analysis: ExecutionFailureAnalysis,
        project_id: UUID | str | None = None,
    ) -> PreparedKnowledgeDocument:
        """
        Prepare an ExecutionFailureAnalysis record into a searchable document.
        Maintains the critical distinction between an AI-generated diagnostic hypothesis
        and a verified root cause.
        """
        if not getattr(analysis, "id", None) or not getattr(analysis, "summary", None):
            raise ValueError("Failure analysis must have an id and summary to be prepared.")

        resolved_project_id = self.resolve_project_id(analysis, project_id)

        lines: list[str] = [
            f"Failure Analysis: {_clean_str(analysis.failure_category)}",
            f"Diagnostic Confidence: {_clean_str(analysis.confidence).upper()}",
            "",
            "Summary of Failure:",
            _clean_str(analysis.summary),
            "",
            "Observed Error:",
            _clean_str(analysis.observed_error),
            "",
            "Likely Root Cause (AI Hypothesis):",
            _clean_str(analysis.likely_root_cause),
        ]

        # Supporting evidence (capped to 10 items to prevent bloat)
        if analysis.supporting_evidence and isinstance(analysis.supporting_evidence, list):
            lines.extend(["", "Supporting Telemetry / Evidence:"])
            for ev in analysis.supporting_evidence[:10]:
                cleaned = _clean_str(ev)
                if cleaned:
                    lines.append(f"- {cleaned}")

        # Recommended debugging steps (capped to 10 items)
        if analysis.recommended_debugging_steps and isinstance(analysis.recommended_debugging_steps, list):
            lines.extend(["", "Recommended Debugging Actions:"])
            for step in analysis.recommended_debugging_steps[:10]:
                cleaned = _clean_str(step)
                if cleaned:
                    lines.append(f"- {cleaned}")

        # Explicit hypothesis demarcation
        lines.extend([
            "",
            "Diagnostic Epistemic Status: AI-generated root-cause diagnosis. "
            "This is a diagnostic hypothesis, NOT a confirmed code fix or verified resolution.",
        ])

        search_text = "\n".join(lines)

        metadata: dict[str, Any] = {
            "record_type": KnowledgeRecordType.FAILURE_ANALYSIS.value,
            "source_id": str(analysis.id),
            "project_id": resolved_project_id,
            "execution_id": str(analysis.execution_id),
            "failure_category": analysis.failure_category,
            "confidence": analysis.confidence,
            "is_verified_resolution": False,
            "is_ai_hypothesis": True,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        }

        doc_title = f"Failure Analysis: {analysis.failure_category} - {analysis.summary[:80]}"

        return PreparedKnowledgeDocument(
            record_type=KnowledgeRecordType.FAILURE_ANALYSIS,
            source_id=str(analysis.id),
            project_id=resolved_project_id,
            title=doc_title,
            search_text=search_text,
            is_verified_resolution=False,
            metadata=metadata,
            created_at=analysis.created_at,
        )

    def prepare_test_case(
        self,
        test_case: TestCase,
        project_id: UUID | str | None = None,
    ) -> PreparedKnowledgeDocument:
        """
        Prepare a TestCase record into a searchable document.
        Serializes preconditions, structured steps, and expected outcomes into clean search text.
        """
        if not getattr(test_case, "id", None) or not getattr(test_case, "title", None):
            raise ValueError("Test case must have an id and title to be prepared.")

        resolved_project_id = self.resolve_project_id(test_case, project_id)

        lines: list[str] = [
            f"Test Case: {_clean_str(test_case.title)}",
            f"Type: {test_case.test_type.value.upper()} | Priority: {test_case.priority.value.upper()}",
            f"Review Status: {test_case.review_status.value.upper()} | Version: v{test_case.version}",
        ]

        if test_case.description:
            lines.extend(["", "Description:", _clean_str(test_case.description)])

        if test_case.target_url:
            lines.extend(["", f"Target URL: {_clean_str(test_case.target_url)}"])

        # Preconditions
        if test_case.preconditions and isinstance(test_case.preconditions, list):
            lines.extend(["", "Preconditions:"])
            for pre in test_case.preconditions:
                cleaned = _clean_str(pre)
                if cleaned:
                    lines.append(f"- {cleaned}")

        # Structured Steps
        if test_case.steps and isinstance(test_case.steps, list):
            lines.extend(["", "Execution Steps:"])
            for idx, s in enumerate(test_case.steps, start=1):
                if isinstance(s, dict):
                    action = _clean_str(s.get("action", ""))
                    expected = _clean_str(s.get("expected_result") or s.get("expected", ""))
                    step_line = f"Step {idx}: {action}"
                    if expected:
                        step_line += f" (Expected: {expected})"
                    lines.append(step_line)
                elif isinstance(s, str):
                    lines.append(f"Step {idx}: {_clean_str(s)}")

        # Expected Result
        lines.extend([
            "",
            "Expected Final Result:",
            _clean_str(test_case.expected_result or "Unspecified"),
        ])

        search_text = "\n".join(lines)

        metadata: dict[str, Any] = {
            "record_type": KnowledgeRecordType.TEST_CASE.value,
            "source_id": str(test_case.id),
            "project_id": resolved_project_id,
            "requirement_id": str(test_case.requirement_id),
            "test_type": test_case.test_type.value,
            "priority": test_case.priority.value,
            "status": test_case.status.value,
            "review_status": test_case.review_status.value,
            "version": test_case.version,
            "is_verified_resolution": False,
            "created_at": test_case.created_at.isoformat() if test_case.created_at else None,
        }

        return PreparedKnowledgeDocument(
            record_type=KnowledgeRecordType.TEST_CASE,
            source_id=str(test_case.id),
            project_id=resolved_project_id,
            title=test_case.title,
            search_text=search_text,
            is_verified_resolution=False,
            metadata=metadata,
            created_at=test_case.created_at,
        )

    # -------------------------------------------------------------------------
    # Database Query Helpers (When Session is injected)
    # -------------------------------------------------------------------------

    def get_preparable_defects(self, project_id: UUID) -> list[PreparedKnowledgeDocument]:
        """Fetch and prepare all defects belonging to a project."""
        if self.db is None:
            raise RuntimeError("Database session is required to fetch preparable defects.")

        statement = (
            select(Defect)
            .join(TestExecution)
            .join(TestCase)
            .join(Requirement)
            .where(Requirement.project_id == project_id)
            .options(
                selectinload(Defect.execution)
                .selectinload(TestExecution.test_case)
                .selectinload(TestCase.requirement)
            )
            .order_by(Defect.created_at.asc())
        )
        defects = list(self.db.scalars(statement))
        return [self.prepare_defect(d, project_id=project_id) for d in defects]

    def get_preparable_failure_analyses(self, project_id: UUID) -> list[PreparedKnowledgeDocument]:
        """Fetch and prepare all failure analyses belonging to a project."""
        if self.db is None:
            raise RuntimeError("Database session is required to fetch preparable failure analyses.")

        statement = (
            select(ExecutionFailureAnalysis)
            .where(ExecutionFailureAnalysis.project_id == project_id)
            .order_by(ExecutionFailureAnalysis.created_at.asc())
        )
        analyses = list(self.db.scalars(statement))
        return [self.prepare_failure_analysis(a, project_id=project_id) for a in analyses]

    def get_preparable_test_cases(self, project_id: UUID) -> list[PreparedKnowledgeDocument]:
        """Fetch and prepare all test cases belonging to a project."""
        if self.db is None:
            raise RuntimeError("Database session is required to fetch preparable test cases.")

        statement = (
            select(TestCase)
            .join(Requirement)
            .where(Requirement.project_id == project_id)
            .options(selectinload(TestCase.requirement))
            .order_by(TestCase.created_at.asc())
        )
        test_cases = list(self.db.scalars(statement))
        return [self.prepare_test_case(tc, project_id=project_id) for tc in test_cases]

    def prepare_all_project_knowledge(self, project_id: UUID) -> list[PreparedKnowledgeDocument]:
        """Fetch and prepare all historical knowledge (defects, analyses, test cases) for a project."""
        documents: list[PreparedKnowledgeDocument] = []
        documents.extend(self.get_preparable_defects(project_id))
        documents.extend(self.get_preparable_failure_analyses(project_id))
        documents.extend(self.get_preparable_test_cases(project_id))
        return documents
