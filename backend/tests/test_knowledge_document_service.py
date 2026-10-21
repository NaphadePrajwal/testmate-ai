from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.defect import Defect
from app.models.enums import (
    DefectStatus,
    Priority,
    ReviewStatus,
    Severity,
    TestCaseStatus,
    TestType,
    VerificationStatus,
)
from app.models.execution_failure_analysis import ExecutionFailureAnalysis
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import ExecutionStatus, TestExecution
from app.schemas.knowledge import KnowledgeRecordType, PreparedKnowledgeDocument
from app.services.knowledge_document_service import KnowledgeDocumentService


def test_prepare_unresolved_defect() -> None:
    """Verify unresolved defect is prepared with clean search_text, metadata, and no fabricated claims."""
    project_id = uuid4()
    defect = Defect(
        id=uuid4(),
        execution_id=uuid4(),
        title="Payment gateway timeout",
        description="Checkout fails when paying with credit card after 30 seconds.",
        severity=Severity.HIGH,
        status=DefectStatus.NEW,
        fingerprint="payment-gateway-timeout-hash",
        created_at=datetime.now(timezone.utc),
    )

    service = KnowledgeDocumentService()
    doc = service.prepare_defect(defect, project_id=project_id)

    assert isinstance(doc, PreparedKnowledgeDocument)
    assert doc.record_type == KnowledgeRecordType.DEFECT
    assert doc.source_id == str(defect.id)
    assert doc.project_id == str(project_id)
    assert doc.title == "Payment gateway timeout"
    assert doc.is_verified_resolution is False

    # Check search text
    assert "Defect Title: Payment gateway timeout" in doc.search_text
    assert "Severity: HIGH" in doc.search_text
    assert "Current Status: NEW" in doc.search_text
    assert "Checkout fails when paying with credit card" in doc.search_text
    assert "Unresolved active defect (NEW)" in doc.search_text

    # Check metadata
    assert doc.metadata["record_type"] == "defect"
    assert doc.metadata["source_id"] == str(defect.id)
    assert doc.metadata["project_id"] == str(project_id)
    assert doc.metadata["severity"] == "high"
    assert doc.metadata["status"] == "new"
    assert doc.metadata["fingerprint"] == "payment-gateway-timeout-hash"
    assert doc.metadata["is_verified_resolution"] is False
    assert doc.metadata["has_verified_root_cause"] is False


def test_prepare_resolved_defect_does_not_fabricate_root_cause() -> None:
    """Verify resolved defect is marked resolved but explicitly notes lack of verified root-cause document."""
    project_id = uuid4()
    defect = Defect(
        id=uuid4(),
        execution_id=uuid4(),
        title="Session cookie expired prematurely",
        description="User was logged out after 2 minutes instead of 30 minutes.",
        severity=Severity.MEDIUM,
        status=DefectStatus.RESOLVED,
        verification_status=VerificationStatus.UNVERIFIED,
        created_at=datetime.now(timezone.utc),
    )

    service = KnowledgeDocumentService()
    doc = service.prepare_defect(defect, project_id=project_id)

    assert doc.is_verified_resolution is False
    assert "Resolution Status: Defect is marked as RESOLVED in defect tracker" in doc.search_text
    assert "No verified post-mortem root-cause documentation recorded" in doc.search_text
    assert doc.metadata["is_verified_resolution"] is False
    assert doc.metadata["has_verified_root_cause"] is False


def test_prepare_verified_defect_includes_technical_resolution() -> None:
    """Verify defect with verified resolution includes explicit technical fix and evidence in search_text and metadata."""
    project_id = uuid4()
    defect = Defect(
        id=uuid4(),
        execution_id=uuid4(),
        title="Race condition in payment webhook",
        description="Double credit applied when webhook retried within 100ms.",
        severity=Severity.CRITICAL,
        status=DefectStatus.RESOLVED,
        verification_status=VerificationStatus.VERIFIED,
        resolution_notes="Added idempotency key constraint in Postgres payment_events table.",
        verification_method="regression_test",
        verification_evidence="exec-12345 passed",
        verified_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )

    service = KnowledgeDocumentService()
    doc = service.prepare_defect(defect, project_id=project_id)

    assert doc.is_verified_resolution is True
    assert "Resolution Status: VERIFIED TECHNICAL FIX" in doc.search_text
    assert "Added idempotency key constraint" in doc.search_text
    assert "Verification Method: regression_test" in doc.search_text
    assert "Verification Evidence: exec-12345 passed" in doc.search_text
    assert doc.metadata["is_verified_resolution"] is True
    assert doc.metadata["has_verified_root_cause"] is True
    assert doc.metadata["verification_status"] == "verified"
    assert doc.metadata["resolution_notes"] == "Added idempotency key constraint in Postgres payment_events table."
    assert doc.metadata["verification_method"] == "regression_test"


def test_prepare_failure_analysis_maintains_hypothesis_distinction() -> None:
    """Verify failure analysis preserves AI-generated hypothesis status and does not claim verified fact."""
    project_id = uuid4()
    analysis = ExecutionFailureAnalysis(
        id=uuid4(),
        execution_id=uuid4(),
        project_id=project_id,
        failure_category="timeout",
        summary="Navigation timed out while waiting for dashboard element.",
        observed_error="Playwright TimeoutError: locator.click: Timeout 15000ms exceeded.",
        likely_root_cause="The backend /api/v1/projects endpoint took >15s due to unindexed database query.",
        supporting_evidence=["Network trace shows GET /api/v1/projects pending for 14.8s", "DOM screenshot displays loading spinner"],
        recommended_debugging_steps=["Inspect PostgreSQL query execution plan", "Add index on projects.created_at"],
        confidence="high",
        created_at=datetime.now(timezone.utc),
    )

    service = KnowledgeDocumentService()
    doc = service.prepare_failure_analysis(analysis)

    assert doc.record_type == KnowledgeRecordType.FAILURE_ANALYSIS
    assert doc.source_id == str(analysis.id)
    assert doc.project_id == str(project_id)
    assert doc.is_verified_resolution is False

    # Check search text
    assert "Failure Analysis: timeout" in doc.search_text
    assert "Likely Root Cause (AI Hypothesis):" in doc.search_text
    assert "The backend /api/v1/projects endpoint took >15s" in doc.search_text
    assert "Network trace shows GET /api/v1/projects pending for 14.8s" in doc.search_text
    assert "Inspect PostgreSQL query execution plan" in doc.search_text
    assert "This is a diagnostic hypothesis, NOT a confirmed code fix" in doc.search_text

    # Check metadata
    assert doc.metadata["is_verified_resolution"] is False
    assert doc.metadata["is_ai_hypothesis"] is True
    assert doc.metadata["failure_category"] == "timeout"
    assert doc.metadata["confidence"] == "high"


def test_prepare_test_case_serializes_structured_steps_and_preconditions() -> None:
    """Verify test case serialization handles preconditions, structured steps, and missing description."""
    project_id = uuid4()
    req_id = uuid4()
    test_case = TestCase(
        id=uuid4(),
        requirement_id=req_id,
        title="Verify successful user login",
        description=None,  # Missing optional description
        target_url="https://app.example.com/login",
        preconditions=["User account exists with email test@example.com", "Browser is open"],
        steps=[
            {"step_index": 1, "action": "Fill email field with test@example.com", "expected_result": "Email populated"},
            {"step_index": 2, "action": "Click submit button", "expected_result": "Redirected to /dashboard"},
        ],
        expected_result="User is authenticated and view dashboard page.",
        test_type=TestType.WEB,
        priority=Priority.HIGH,
        status=TestCaseStatus.APPROVED,
        review_status=ReviewStatus.APPROVED,
        version=2,
        created_at=datetime.now(timezone.utc),
    )

    service = KnowledgeDocumentService()
    doc = service.prepare_test_case(test_case, project_id=project_id)

    assert doc.record_type == KnowledgeRecordType.TEST_CASE
    assert doc.source_id == str(test_case.id)
    assert doc.project_id == str(project_id)
    assert doc.title == "Verify successful user login"
    assert doc.is_verified_resolution is False

    # Check search text formatting
    assert "Test Case: Verify successful user login" in doc.search_text
    assert "Target URL: https://app.example.com/login" in doc.search_text
    assert "User account exists with email test@example.com" in doc.search_text
    assert "Step 1: Fill email field with test@example.com (Expected: Email populated)" in doc.search_text
    assert "Step 2: Click submit button (Expected: Redirected to /dashboard)" in doc.search_text
    assert "Expected Final Result:\nUser is authenticated and view dashboard page." in doc.search_text

    # Check metadata
    assert doc.metadata["record_type"] == "test_case"
    assert doc.metadata["test_type"] == "web"
    assert doc.metadata["priority"] == "high"
    assert doc.metadata["status"] == "approved"
    assert doc.metadata["review_status"] == "approved"
    assert doc.metadata["version"] == 2


def test_project_id_resolution_failure_raises_value_error() -> None:
    """Verify that an entity whose project_id cannot be authoritatively resolved raises ValueError."""
    defect = Defect(id=uuid4(), title="Detached defect", description="desc", execution_id=uuid4())
    service = KnowledgeDocumentService()

    with pytest.raises(ValueError, match="Cannot resolve authoritative project_id"):
        service.prepare_defect(defect)


def test_invalid_entities_raise_value_error() -> None:
    """Verify missing required identifiers or core fields raise ValueError."""
    service = KnowledgeDocumentService()

    # Defect without id
    with pytest.raises(ValueError, match="Defect must have an id and title"):
        service.prepare_defect(Defect(id=None, title="bad defect"))  # type: ignore[arg-type]

    # Failure analysis without summary
    with pytest.raises(ValueError, match="Failure analysis must have an id and summary"):
        service.prepare_failure_analysis(ExecutionFailureAnalysis(id=uuid4(), summary=""))

    # Test case without title
    with pytest.raises(ValueError, match="Test case must have an id and title"):
        service.prepare_test_case(TestCase(id=uuid4(), title=""))


def test_database_batch_knowledge_preparation(db_session: Session) -> None:
    """Verify batch retrieval and preparation of all project knowledge from PostgreSQL."""
    # 1. Create project & requirement
    project = Project(id=uuid4(), name="E-Commerce QA Project", description="Main web app")
    db_session.add(project)
    db_session.flush()

    req = Requirement(
        id=uuid4(),
        project_id=project.id,
        title="User Registration",
        description="Allows new customers to sign up",
    )
    db_session.add(req)
    db_session.flush()

    # 2. Create test case
    tc = TestCase(
        id=uuid4(),
        requirement_id=req.id,
        title="Register with existing email",
        description="Expect error on duplicate email",
        expected_result="Displays 'Email already registered' error message",
        test_type=TestType.WEB,
        priority=Priority.MEDIUM,
        status=TestCaseStatus.APPROVED,
        review_status=ReviewStatus.APPROVED,
        steps=[{"action": "Enter existing email", "expected": "Validation error"}],
    )
    db_session.add(tc)
    db_session.flush()

    # 3. Create execution
    execution = TestExecution(
        id=uuid4(),
        test_case_id=tc.id,
        status=ExecutionStatus.FAILED,
        error_message="AssertionError: Expected error message not visible",
    )
    db_session.add(execution)
    db_session.flush()

    # 4. Create defect
    defect = Defect(
        id=uuid4(),
        execution_id=execution.id,
        title="Duplicate email validation missing",
        description="System created duplicate user account without error.",
        severity=Severity.HIGH,
        status=DefectStatus.NEW,
    )
    db_session.add(defect)

    # 5. Create failure analysis
    analysis = ExecutionFailureAnalysis(
        id=uuid4(),
        execution_id=execution.id,
        project_id=project.id,
        failure_category="assertion_failure",
        summary="Server responded with 200 OK instead of 409 Conflict.",
        observed_error="Status code 200 returned.",
        likely_root_cause="User registration controller omits uniqueness constraint check.",
        supporting_evidence=["HTTP response body contains newly generated customer ID."],
        recommended_debugging_steps=["Inspect AuthController.registerUser method."],
        confidence="high",
    )
    db_session.add(analysis)
    db_session.commit()

    # 6. Test KnowledgeDocumentService queries
    service = KnowledgeDocumentService(db=db_session)
    docs = service.prepare_all_project_knowledge(project.id)

    assert len(docs) == 3
    types = {d.record_type for d in docs}
    assert types == {
        KnowledgeRecordType.DEFECT,
        KnowledgeRecordType.FAILURE_ANALYSIS,
        KnowledgeRecordType.TEST_CASE,
    }

    # All documents must carry the exact project_id
    for d in docs:
        assert d.project_id == str(project.id)
        assert len(d.search_text) > 0
        assert len(d.title) > 0
