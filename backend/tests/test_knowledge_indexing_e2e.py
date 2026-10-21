import hashlib
import math
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.defect import Defect
from app.models.enums import DefectStatus, Priority, ReviewStatus, Severity, TestCaseStatus, TestType, VerificationStatus
from app.models.execution_failure_analysis import ExecutionFailureAnalysis
from app.models.knowledge_indexing_job import IndexingJobAction, IndexingJobStatus, KnowledgeIndexingJob
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import ExecutionStatus, TestExecution
from app.schemas.execution import DefectUpdate
from app.schemas.failure_analysis import FailureAnalysisContent, FailureCategory
from app.schemas.knowledge import KnowledgeRecordType
from app.services.embedding_service import EmbeddingService
from app.services.execution_service import ExecutionService
from app.services.failure_analysis_service import FailureAnalysisService
from app.services.knowledge_base_service import KnowledgeBaseService, generate_point_id
from app.services.knowledge_document_service import KnowledgeDocumentService
from app.services.knowledge_indexing_job_service import KnowledgeIndexingJobService
from app.services.knowledge_retrieval_service import KnowledgeRetrievalService
from app.services.qdrant_service import QdrantOperatingMode, QdrantService
from app.services.test_case_service import TestCaseService


class DeterministicE2EEmbeddingService(EmbeddingService):
    """
    Deterministic embedding double producing normalized 384-d vectors without downloading ML models.
    Uses token hashing so that queries sharing significant semantic words have high cosine similarity.
    """

    def __init__(self) -> None:
        pass

    def embed_text(self, text: str) -> list[float]:
        # Normalize punctuation and tokenize
        words = text.lower().replace(":", " ").replace("-", " ").replace("|", " ").replace("_", " ").split()
        if not words:
            words = ["empty"]
        vec = [0.0] * 384
        for word in words:
            h = hashlib.sha256(word.encode("utf-8")).digest()
            for i in range(384):
                b = h[i % len(h)]
                vec[i] += float((b % 100) - 50)
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


@pytest.fixture
def e2e_qdrant() -> QdrantService:
    settings = Settings(
        qdrant_mode="memory",
        qdrant_collection=f"test_e2e_{uuid4().hex[:8]}",
        qdrant_vector_size=384,
    )
    svc = QdrantService(settings=settings, mode=QdrantOperatingMode.MEMORY)
    svc.ensure_collection()
    return svc


@pytest.fixture
def e2e_embedding() -> EmbeddingService:
    return DeterministicE2EEmbeddingService()


@pytest.fixture
def e2e_kb_service(db_session: Session, e2e_qdrant: QdrantService, e2e_embedding: EmbeddingService) -> KnowledgeBaseService:
    return KnowledgeBaseService(
        db=db_session,
        qdrant_service=e2e_qdrant,
        embedding_service=e2e_embedding,
        document_service=KnowledgeDocumentService(db=db_session),
    )


@pytest.fixture
def e2e_job_service(db_session: Session, e2e_kb_service: KnowledgeBaseService) -> KnowledgeIndexingJobService:
    return KnowledgeIndexingJobService(
        db=db_session,
        knowledge_base_service=e2e_kb_service,
    )


@pytest.fixture
def e2e_retrieval_service(db_session: Session, e2e_qdrant: QdrantService, e2e_embedding: EmbeddingService) -> KnowledgeRetrievalService:
    return KnowledgeRetrievalService(
        db=db_session,
        qdrant_service=e2e_qdrant,
        embedding_service=e2e_embedding,
    )


def _setup_project_hierarchy(db: Session) -> tuple[Project, Requirement, TestCase, TestExecution]:
    project = Project(name=f"E2E RAG Project {uuid4().hex[:6]}", description="Phase 8.8 testing")
    db.add(project)
    db.commit()

    req = Requirement(project_id=project.id, title="Checkout Payment", description="Payment flow")
    db.add(req)
    db.commit()

    tc = TestCase(
        requirement_id=req.id,
        title="Credit Card Checkout",
        description="Verify credit card purchase",
        expected_result="Order confirmation",
        priority=Priority.HIGH,
        test_type=TestType.WEB,
        status=TestCaseStatus.APPROVED,
        review_status=ReviewStatus.APPROVED,
    )
    db.add(tc)
    db.commit()

    execution = TestExecution(
        test_case_id=tc.id,
        status=ExecutionStatus.FAILED,
        error_message="Gateway timeout connecting to Stripe API after 30000ms",
    )
    db.add(execution)
    db.commit()

    return project, req, tc, execution


# -----------------------------------------------------------------------------
# Scenario A — New failure analysis automatic indexing & searchability
# -----------------------------------------------------------------------------

def test_scenario_a_new_failure_analysis_auto_indexed(
    db_session: Session,
    e2e_kb_service: KnowledgeBaseService,
    e2e_job_service: KnowledgeIndexingJobService,
    e2e_retrieval_service: KnowledgeRetrievalService,
) -> None:
    project, req, tc, execution = _setup_project_hierarchy(db_session)

    mock_provider = MagicMock()
    mock_provider.provider_name = "test_provider"
    mock_provider.model_name = "test_model"
    mock_provider.analyze.return_value = FailureAnalysisContent(
        failure_category=FailureCategory.INFRASTRUCTURE_ERROR,
        summary="Payment gateway timed out due to network latency.",
        observed_error=execution.error_message,
        likely_root_cause="Stripe sandbox gateway unreachable from test container.",
        supporting_evidence=["HTTP 504 Gateway Timeout"],
        recommended_debugging_steps=["Check outbound network egress"],
        confidence="high",
        uncertainty_notes=None,
    )

    fa_service = FailureAnalysisService(
        db=db_session,
        provider=mock_provider,
        retrieval_service=e2e_retrieval_service,
        job_service=e2e_job_service,
    )

    analysis = fa_service.get_or_create_analysis(project.id, execution.id)
    assert analysis is not None

    # Verify searchability
    search_res = e2e_retrieval_service.search_project_knowledge(
        project_id=project.id,
        query="gateway timeout connecting to Stripe API",
        limit=5,
    )
    assert search_res.total_found >= 1
    found_types = [c.record_type for c in search_res.candidates]
    assert KnowledgeRecordType.FAILURE_ANALYSIS in found_types


# -----------------------------------------------------------------------------
# Scenario B — Future similar failure retrieves historical context
# -----------------------------------------------------------------------------

def test_scenario_b_future_similar_failure_retrieval(
    db_session: Session,
    e2e_kb_service: KnowledgeBaseService,
    e2e_retrieval_service: KnowledgeRetrievalService,
) -> None:
    project, req, tc, execution1 = _setup_project_hierarchy(db_session)

    # 1. Store and index first failure analysis
    analysis1 = ExecutionFailureAnalysis(
        execution_id=execution1.id,
        project_id=project.id,
        failure_category=FailureCategory.INFRASTRUCTURE_ERROR.value,
        summary="Payment gateway timeout",
        observed_error=execution1.error_message,
        likely_root_cause="Stripe sandbox DNS resolution failure",
        supporting_evidence=["DNS SERVFAIL"],
        recommended_debugging_steps=["Check DNS servers"],
        confidence="high",
    )
    db_session.add(analysis1)
    db_session.commit()
    e2e_kb_service.index_single_failure_analysis(analysis1, project_id=project.id)

    # 2. Create second failed execution with similar error
    execution2 = TestExecution(
        test_case_id=tc.id,
        status=ExecutionStatus.FAILED,
        error_message="Gateway timeout connecting to Stripe API after 30000ms",
    )
    db_session.add(execution2)
    db_session.commit()

    captured_context = None

    class CaptureProvider:
        provider_name = "capture"
        model_name = "test"

        def analyze(self, ctx):
            nonlocal captured_context
            captured_context = ctx
            return FailureAnalysisContent(
                failure_category=FailureCategory.INFRASTRUCTURE_ERROR,
                summary="Recurrent timeout detected",
                observed_error=ctx.error_message or "Gateway timeout",
                likely_root_cause="Recurrent Stripe sandbox network timeout",
                supporting_evidence=[],
                recommended_debugging_steps=[],
                confidence="high",
            )

    fa_service = FailureAnalysisService(
        db=db_session,
        provider=CaptureProvider(),
        retrieval_service=e2e_retrieval_service,
    )
    fa_service.get_or_create_analysis(project.id, execution2.id)

    assert captured_context is not None
    assert len(captured_context.historical_candidates) >= 1
    top_cand = captured_context.historical_candidates[0]
    assert top_cand.source_id == str(analysis1.id)


# -----------------------------------------------------------------------------
# Scenario C — Defect resolution lifecycle
# -----------------------------------------------------------------------------

def test_scenario_c_defect_resolution_lifecycle(
    db_session: Session,
    e2e_kb_service: KnowledgeBaseService,
    e2e_retrieval_service: KnowledgeRetrievalService,
) -> None:
    project, req, tc, execution = _setup_project_hierarchy(db_session)
    exec_service = ExecutionService(db=db_session)

    defect = Defect(
        execution_id=execution.id,
        title="Double charge on retry",
        description="User charged twice when connection reset during checkout.",
        severity=Severity.CRITICAL,
        status=DefectStatus.NEW,
    )
    db_session.add(defect)
    db_session.commit()

    # Step 1: Mark resolved WITHOUT technical verification
    exec_service.update_defect(
        project.id,
        defect.id,
        DefectUpdate(status=DefectStatus.RESOLVED),
    )
    doc_unverified = KnowledgeDocumentService(db=db_session).prepare_defect(defect, project_id=project.id)
    assert doc_unverified.is_verified_resolution is False
    assert "No verified post-mortem root-cause documentation recorded" in doc_unverified.search_text

    # Step 2: Record technical fix and verify resolution
    exec_service.update_defect(
        project.id,
        defect.id,
        DefectUpdate(
            resolution_notes="Implemented Idempotency-Key header on Stripe charges table.",
            verification_status=VerificationStatus.VERIFIED,
            verification_method="regression_test",
            verification_evidence="TestExecution-456 passed",
        ),
    )
    doc_verified = KnowledgeDocumentService(db=db_session).prepare_defect(defect, project_id=project.id)
    assert doc_verified.is_verified_resolution is True
    assert "Resolution Status: VERIFIED TECHNICAL FIX" in doc_verified.search_text
    assert "Implemented Idempotency-Key header" in doc_verified.search_text
    assert doc_verified.metadata["verification_method"] == "regression_test"

    # Step 3: Revoke verification
    exec_service.update_defect(
        project.id,
        defect.id,
        DefectUpdate(verification_status=VerificationStatus.REVOKED),
    )
    doc_revoked = KnowledgeDocumentService(db=db_session).prepare_defect(defect, project_id=project.id)
    assert doc_revoked.is_verified_resolution is False


# -----------------------------------------------------------------------------
# Scenario D — Indexing failure and retry
# -----------------------------------------------------------------------------

def test_scenario_d_indexing_failure_and_retry(
    db_session: Session,
    e2e_kb_service: KnowledgeBaseService,
) -> None:
    project, req, tc, execution = _setup_project_hierarchy(db_session)

    defect = Defect(
        execution_id=execution.id,
        title="Cache eviction failure",
        description="Redis cluster timeout during eviction.",
        severity=Severity.HIGH,
        status=DefectStatus.NEW,
    )
    db_session.add(defect)
    db_session.commit()

    failing_kb = MagicMock()
    failing_kb.index_single_defect.side_effect = RuntimeError("Qdrant connection refused: 6333")

    job_service = KnowledgeIndexingJobService(db=db_session, knowledge_base_service=failing_kb)
    job = job_service.enqueue_job(project.id, KnowledgeRecordType.DEFECT, defect.id)

    # Primary business record is in DB
    assert db_session.get(Defect, defect.id) is not None

    # Processing fails
    ok = job_service.process_job(job.id)
    assert ok is False
    db_session.refresh(job)
    assert job.status == IndexingJobStatus.PENDING
    assert job.retry_count == 1
    assert "Qdrant connection refused" in (job.last_error or "")

    # Now simulate recovery with working service
    job_service.kb_service = e2e_kb_service
    ok2 = job_service.process_job(job.id)
    assert ok2 is True
    db_session.refresh(job)
    assert job.status == IndexingJobStatus.COMPLETED
    assert job.last_error is None


# -----------------------------------------------------------------------------
# Scenario E — Idempotency
# -----------------------------------------------------------------------------

def test_scenario_e_idempotency_no_duplicate_vector_points(
    db_session: Session,
    e2e_kb_service: KnowledgeBaseService,
    e2e_qdrant: QdrantService,
) -> None:
    project, req, tc, execution = _setup_project_hierarchy(db_session)

    defect = Defect(
        execution_id=execution.id,
        title="Duplicate button click bug",
        description="Button emits two clicks.",
        severity=Severity.LOW,
        status=DefectStatus.NEW,
    )
    db_session.add(defect)
    db_session.commit()

    job_service = KnowledgeIndexingJobService(db=db_session, knowledge_base_service=e2e_kb_service)

    # Enqueue and process 3 times
    for _ in range(3):
        job = job_service.enqueue_job(project.id, KnowledgeRecordType.DEFECT, defect.id)
        job_service.process_job(job.id)

    expected_point_id = generate_point_id(KnowledgeRecordType.DEFECT, str(defect.id))
    points = e2e_qdrant.client.retrieve(
        collection_name=e2e_qdrant.collection_name,
        ids=[expected_point_id],
    )
    assert len(points) == 1
    assert points[0].id == expected_point_id


# -----------------------------------------------------------------------------
# Scenario F — Update synchronization
# -----------------------------------------------------------------------------

def test_scenario_f_update_synchronization(
    db_session: Session,
    e2e_kb_service: KnowledgeBaseService,
    e2e_qdrant: QdrantService,
) -> None:
    project, req, tc, execution = _setup_project_hierarchy(db_session)
    job_service = KnowledgeIndexingJobService(db=db_session, knowledge_base_service=e2e_kb_service)

    defect = Defect(
        execution_id=execution.id,
        title="Original Title",
        description="Initial description",
        severity=Severity.LOW,
        status=DefectStatus.NEW,
    )
    db_session.add(defect)
    db_session.commit()

    # Index original
    job1 = job_service.enqueue_job(project.id, KnowledgeRecordType.DEFECT, defect.id)
    job_service.process_job(job1.id)

    expected_point_id = generate_point_id(KnowledgeRecordType.DEFECT, str(defect.id))
    p1 = e2e_qdrant.client.retrieve(e2e_qdrant.collection_name, [expected_point_id])[0]
    assert p1.payload["title"] == "Original Title"

    # Update defect
    defect.title = "Updated Title After Hotfix"
    defect.status = DefectStatus.RESOLVED
    defect.verification_status = VerificationStatus.VERIFIED
    defect.resolution_notes = "Applied patch 1.0.4"
    db_session.commit()

    # Re-index
    job2 = job_service.enqueue_job(project.id, KnowledgeRecordType.DEFECT, defect.id)
    job_service.process_job(job2.id)

    p2 = e2e_qdrant.client.retrieve(e2e_qdrant.collection_name, [expected_point_id])[0]
    assert p2.payload["title"] == "Updated Title After Hotfix"
    assert p2.payload["is_verified_resolution"] is True
    assert p2.payload["resolution_notes"] == "Applied patch 1.0.4"


# -----------------------------------------------------------------------------
# Scenario G — Project isolation
# -----------------------------------------------------------------------------

def test_scenario_g_project_isolation(
    db_session: Session,
    e2e_kb_service: KnowledgeBaseService,
    e2e_retrieval_service: KnowledgeRetrievalService,
) -> None:
    p1, req1, tc1, exec1 = _setup_project_hierarchy(db_session)
    p2, req2, tc2, exec2 = _setup_project_hierarchy(db_session)

    defect1 = Defect(
        execution_id=exec1.id,
        title="Project One Secret Defect",
        description="Confidential payment key leak in Project 1",
        severity=Severity.CRITICAL,
        status=DefectStatus.NEW,
    )
    defect2 = Defect(
        execution_id=exec2.id,
        title="Project Two Public Defect",
        description="Minor CSS styling defect in Project 2",
        severity=Severity.LOW,
        status=DefectStatus.NEW,
    )
    db_session.add_all([defect1, defect2])
    db_session.commit()

    e2e_kb_service.index_single_defect(defect1, project_id=p1.id)
    e2e_kb_service.index_single_defect(defect2, project_id=p2.id)

    # Search in Project 2 for terms present in Project 1 defect
    res = e2e_retrieval_service.search_project_knowledge(
        project_id=p2.id,
        query="Confidential payment key leak",
        limit=5,
    )
    for cand in res.candidates:
        assert cand.project_id == str(p2.id)
        assert "Project One Secret Defect" not in cand.title


# -----------------------------------------------------------------------------
# Scenario H — Cached analysis skips redundant retrieval and indexing
# -----------------------------------------------------------------------------

def test_scenario_h_cached_analysis_skips_retrieval_and_duplicate_job(
    db_session: Session,
    e2e_retrieval_service: KnowledgeRetrievalService,
) -> None:
    project, req, tc, execution = _setup_project_hierarchy(db_session)

    existing_fa = ExecutionFailureAnalysis(
        execution_id=execution.id,
        project_id=project.id,
        failure_category=FailureCategory.INFRASTRUCTURE_ERROR.value,
        summary="Cached failure analysis",
        observed_error=execution.error_message,
        likely_root_cause="Cached root cause",
        supporting_evidence=[],
        recommended_debugging_steps=[],
        confidence="high",
    )
    db_session.add(existing_fa)
    db_session.commit()

    mock_retrieval = MagicMock()
    mock_provider = MagicMock()

    fa_service = FailureAnalysisService(
        db=db_session,
        provider=mock_provider,
        retrieval_service=mock_retrieval,
    )

    # Calling without force_refresh
    res = fa_service.get_or_create_analysis(project.id, execution.id, force_refresh=False)
    assert res.id == existing_fa.id
    mock_retrieval.search_project_knowledge.assert_not_called()
    mock_provider.analyze.assert_not_called()


# -----------------------------------------------------------------------------
# Scenario I — Restart and recovery of pending jobs
# -----------------------------------------------------------------------------

def test_scenario_i_job_recovery(
    db_session: Session,
    e2e_kb_service: KnowledgeBaseService,
) -> None:
    project, req, tc, execution = _setup_project_hierarchy(db_session)

    defect = Defect(
        execution_id=execution.id,
        title="Abandoned processing bug",
        description="Processing was interrupted midway",
        severity=Severity.HIGH,
        status=DefectStatus.NEW,
    )
    db_session.add(defect)
    db_session.commit()

    # Simulate abandoned pending job
    abandoned_job = KnowledgeIndexingJob(
        project_id=project.id,
        record_type=KnowledgeRecordType.DEFECT.value,
        source_id=defect.id,
        action=IndexingJobAction.UPSERT,
        status=IndexingJobStatus.PENDING,
    )
    db_session.add(abandoned_job)
    db_session.commit()

    job_service = KnowledgeIndexingJobService(db=db_session, knowledge_base_service=e2e_kb_service)
    success, failure = job_service.process_project_jobs(project.id)
    assert success == 1
    assert failure == 0

    db_session.refresh(abandoned_job)
    assert abandoned_job.status == IndexingJobStatus.COMPLETED


# -----------------------------------------------------------------------------
# Scenario J — Malformed or deleted source records
# -----------------------------------------------------------------------------

def test_scenario_j_deleted_source_record_cleans_vector(
    db_session: Session,
    e2e_kb_service: KnowledgeBaseService,
    e2e_qdrant: QdrantService,
) -> None:
    project, req, tc, execution = _setup_project_hierarchy(db_session)

    defect = Defect(
        execution_id=execution.id,
        title="Defect to delete",
        description="Will be removed",
        severity=Severity.LOW,
        status=DefectStatus.NEW,
    )
    db_session.add(defect)
    db_session.commit()

    # Index it
    e2e_kb_service.index_single_defect(defect, project_id=project.id)
    pid = generate_point_id(KnowledgeRecordType.DEFECT, str(defect.id))
    assert len(e2e_qdrant.client.retrieve(e2e_qdrant.collection_name, [pid])) == 1

    # Delete source record from DB
    defect_id = defect.id
    db_session.delete(defect)
    db_session.commit()

    # Process upsert job for non-existent record
    job_service = KnowledgeIndexingJobService(db=db_session, knowledge_base_service=e2e_kb_service)
    job = job_service.enqueue_job(project.id, KnowledgeRecordType.DEFECT, defect_id, IndexingJobAction.UPSERT)
    ok = job_service.process_job(job.id)
    assert ok is True

    # Vector point should be cleaned up
    remaining = e2e_qdrant.client.retrieve(e2e_qdrant.collection_name, [pid])
    assert len(remaining) == 0


# -----------------------------------------------------------------------------
# API Route Integration Tests (Defect update & Jobs endpoints)
# -----------------------------------------------------------------------------

def test_api_defect_verification_and_jobs(
    client: TestClient,
    db_session: Session,
) -> None:
    project, req, tc, execution = _setup_project_hierarchy(db_session)

    defect = Defect(
        execution_id=execution.id,
        title="Login CSRF vulnerability",
        description="Missing CSRF token on POST /login",
        severity=Severity.HIGH,
        status=DefectStatus.NEW,
    )
    db_session.add(defect)
    db_session.commit()

    # 1. Update defect to VERIFIED without resolution notes should fail (409 Conflict)
    bad_res = client.patch(
        f"/api/v1/projects/{project.id}/defects/{defect.id}",
        json={"verification_status": "verified"},
    )
    assert bad_res.status_code == 409

    # 2. Update defect to VERIFIED with resolution notes should succeed (200 OK)
    good_res = client.patch(
        f"/api/v1/projects/{project.id}/defects/{defect.id}",
        json={
            "status": "resolved",
            "resolution_notes": "Added CSRF middleware and token cookie.",
            "verification_status": "verified",
            "verification_method": "manual_audit",
            "verification_evidence": "Security audit checklist item #4",
        },
    )
    assert good_res.status_code == 200
    data = good_res.json()
    assert data["status"] == "resolved"
    assert data["verification_status"] == "verified"
    assert data["resolution_notes"] == "Added CSRF middleware and token cookie."

    # 3. List jobs via GET /jobs
    jobs_res = client.get(f"/api/v1/projects/{project.id}/knowledge/jobs")
    assert jobs_res.status_code == 200
    jobs_data = jobs_res.json()
    assert jobs_data["total"] >= 1

    # 4. Trigger processing via POST /jobs/process
    process_res = client.post(f"/api/v1/projects/{project.id}/knowledge/jobs/process")
    assert process_res.status_code == 200
    proc_data = process_res.json()
    assert "processed_count" in proc_data
