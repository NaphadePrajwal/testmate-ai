import math
import uuid
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from qdrant_client.http.exceptions import ResponseHandlingException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import app
from app.models.defect import Defect
from app.models.enums import DefectStatus, Priority, ReviewStatus, Severity, TestCaseStatus, TestType
from app.models.execution_failure_analysis import ExecutionFailureAnalysis
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import ExecutionStatus, TestExecution
from app.schemas.knowledge import KnowledgeRecordType, PreparedKnowledgeDocument
from app.services.embedding_service import EmbeddingGenerationError, EmbeddingService
from app.services.knowledge_base_service import (
    KnowledgeBaseService,
    generate_point_id,
)
from app.services.qdrant_service import QdrantOperatingMode, QdrantService


class DeterministicEmbeddingService(EmbeddingService):
    """Deterministic test double that generates normalized 384-d vectors without model downloads."""

    def __init__(self) -> None:
        pass

    def embed_text(self, text: str) -> list[float]:
        val = 1.0 / math.sqrt(384)
        return [val] * 384

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results = []
        for i, _ in enumerate(texts):
            val = (i + 1.0) / math.sqrt(384)
            norm = math.sqrt(384 * (val**2))
            unit_val = val / norm
            results.append([unit_val] * 384)
        return results


@pytest.fixture
def memory_qdrant() -> QdrantService:
    settings = Settings(
        qdrant_mode="memory",
        qdrant_collection=f"test_kb_{uuid4().hex[:8]}",
        qdrant_vector_size=384,
    )
    svc = QdrantService(settings=settings, mode=QdrantOperatingMode.MEMORY)
    yield svc
    svc.close()


def test_deterministic_point_id_generation() -> None:
    """Verify point IDs are consistent, collision-resistant, and valid UUID strings."""
    source_uuid = str(uuid4())

    id1 = generate_point_id(KnowledgeRecordType.DEFECT, source_uuid)
    id2 = generate_point_id(KnowledgeRecordType.DEFECT, source_uuid)
    # Idempotent: identical inputs produce identical point IDs
    assert id1 == id2

    # Valid UUID format
    parsed = uuid.UUID(id1)
    assert parsed.version == 5

    # Different record types with same source ID do not collide
    id_analysis = generate_point_id(KnowledgeRecordType.FAILURE_ANALYSIS, source_uuid)
    assert id1 != id_analysis

    # Different source IDs do not collide
    other_source = str(uuid4())
    id_other = generate_point_id(KnowledgeRecordType.DEFECT, other_source)
    assert id1 != id_other


def test_index_documents_idempotency_and_payload_preservation(memory_qdrant: QdrantService) -> None:
    """Verify documents are embedded, stored, and re-indexing updates in-place without duplicate points."""
    emb_service = DeterministicEmbeddingService()
    kb_service = KnowledgeBaseService(qdrant_service=memory_qdrant, embedding_service=emb_service)

    proj_id = str(uuid4())
    source_id = str(uuid4())
    doc = PreparedKnowledgeDocument(
        record_type=KnowledgeRecordType.DEFECT,
        source_id=source_id,
        project_id=proj_id,
        title="Checkout button unresponsive",
        search_text="Checkout button fails to submit cart payload on mobile viewport.",
        is_verified_resolution=False,
        metadata={"severity": "high", "status": "new", "fingerprint": "fp-123"},
    )

    # First index pass
    res1 = kb_service.index_documents([doc])
    assert res1.is_successful is True
    assert res1.total_indexed == 1
    assert res1.total_failed == 0

    col_name = memory_qdrant.collection_name
    info = memory_qdrant.client.get_collection(col_name)
    assert info.points_count == 1

    # Verify stored payload
    point_id = generate_point_id(KnowledgeRecordType.DEFECT, source_id)
    retrieved_points = memory_qdrant.client.retrieve(collection_name=col_name, ids=[point_id], with_payload=True)
    assert len(retrieved_points) == 1
    p = retrieved_points[0]
    assert p.payload["record_type"] == "defect"
    assert p.payload["source_id"] == source_id
    assert p.payload["project_id"] == proj_id
    assert p.payload["title"] == "Checkout button unresponsive"
    assert p.payload["severity"] == "high"
    assert p.payload["is_verified_resolution"] is False

    # Second index pass with updated content (e.g. marked resolved)
    doc_updated = PreparedKnowledgeDocument(
        record_type=KnowledgeRecordType.DEFECT,
        source_id=source_id,
        project_id=proj_id,
        title="Checkout button unresponsive",
        search_text="Updated: defect marked resolved after mobile CSS fix.",
        is_verified_resolution=True,
        metadata={"severity": "high", "status": "resolved", "fingerprint": "fp-123"},
    )
    res2 = kb_service.index_documents([doc_updated])
    assert res2.is_successful is True
    assert res2.total_indexed == 1

    # Points count must still be exactly 1 (no duplicate points created)
    info_after = memory_qdrant.client.get_collection(col_name)
    assert info_after.points_count == 1

    # Payload must be updated
    p_updated = memory_qdrant.client.retrieve(collection_name=col_name, ids=[point_id], with_payload=True)[0]
    assert p_updated.payload["is_verified_resolution"] is True
    assert "Updated: defect marked resolved" in p_updated.payload["search_text"]


def test_batch_indexing_all_record_types(memory_qdrant: QdrantService) -> None:
    """Verify batch indexing handles defects, failure analyses, and test cases simultaneously."""
    emb_service = DeterministicEmbeddingService()
    kb_service = KnowledgeBaseService(qdrant_service=memory_qdrant, embedding_service=emb_service)

    proj_id = str(uuid4())
    docs = [
        PreparedKnowledgeDocument(
            record_type=KnowledgeRecordType.DEFECT,
            source_id=str(uuid4()),
            project_id=proj_id,
            title="Defect 1",
            search_text="Defect description 1",
        ),
        PreparedKnowledgeDocument(
            record_type=KnowledgeRecordType.FAILURE_ANALYSIS,
            source_id=str(uuid4()),
            project_id=proj_id,
            title="Failure Analysis 1",
            search_text="Failure Analysis summary 1",
        ),
        PreparedKnowledgeDocument(
            record_type=KnowledgeRecordType.TEST_CASE,
            source_id=str(uuid4()),
            project_id=proj_id,
            title="Test Case 1",
            search_text="Test Case description 1",
        ),
    ]

    res = kb_service.index_documents(docs, batch_size=2)
    assert res.is_successful is True
    assert res.total_indexed == 3
    assert res.total_failed == 0

    info = memory_qdrant.client.get_collection(memory_qdrant.collection_name)
    assert info.points_count == 3


def test_database_project_scoped_indexing(db_session: Session, memory_qdrant: QdrantService) -> None:
    """Verify that project-scoped indexing respects tenant isolation between Project A and Project B."""
    emb_service = DeterministicEmbeddingService()
    kb_service = KnowledgeBaseService(
        db=db_session,
        qdrant_service=memory_qdrant,
        embedding_service=emb_service,
    )

    # Project A
    proj_a = Project(id=uuid4(), name="Project Alpha")
    db_session.add(proj_a)
    req_a = Requirement(id=uuid4(), project_id=proj_a.id, title="Req Alpha", description="Alpha description")
    db_session.add(req_a)
    tc_a = TestCase(
        id=uuid4(),
        requirement_id=req_a.id,
        title="TC Alpha",
        expected_result="Pass Alpha",
        test_type=TestType.WEB,
        steps=[],
    )
    db_session.add(tc_a)

    # Project B
    proj_b = Project(id=uuid4(), name="Project Beta")
    db_session.add(proj_b)
    req_b = Requirement(id=uuid4(), project_id=proj_b.id, title="Req Beta", description="Beta description")
    db_session.add(req_b)
    tc_b = TestCase(
        id=uuid4(),
        requirement_id=req_b.id,
        title="TC Beta",
        expected_result="Pass Beta",
        test_type=TestType.API,
        steps=[],
    )
    db_session.add(tc_b)
    db_session.commit()

    # Index only Project A
    res_a = kb_service.index_project_knowledge(project_id=proj_a.id)
    assert res_a.is_successful is True
    assert res_a.total_indexed == 1  # 1 test case for Project A

    info = memory_qdrant.client.get_collection(memory_qdrant.collection_name)
    assert info.points_count == 1

    # Verify point payload is strictly tagged with project A's ID
    pt_id = generate_point_id(KnowledgeRecordType.TEST_CASE, str(tc_a.id))
    pt = memory_qdrant.client.retrieve(collection_name=memory_qdrant.collection_name, ids=[pt_id])[0]
    assert pt.payload["project_id"] == str(proj_a.id)


def test_embedding_failure_handling(memory_qdrant: QdrantService) -> None:
    """Verify that embedding generation errors are safely trapped and reported in partial results."""
    mock_emb = MagicMock(spec=EmbeddingService)
    mock_emb.embed_batch.side_effect = EmbeddingGenerationError("Simulated embedding pipeline timeout")

    kb_service = KnowledgeBaseService(qdrant_service=memory_qdrant, embedding_service=mock_emb)

    docs = [
        PreparedKnowledgeDocument(
            record_type=KnowledgeRecordType.DEFECT,
            source_id="def-1",
            project_id=str(uuid4()),
            title="Broken checkout",
            search_text="Checkout fails",
        )
    ]

    res = kb_service.index_documents(docs)
    assert res.is_successful is False
    assert res.total_indexed == 0
    assert res.total_failed == 1
    assert len(res.errors) == 1
    assert "Embedding generation failure" in res.errors[0].error


def test_qdrant_upsert_failure_handling(memory_qdrant: QdrantService) -> None:
    """Verify that Qdrant upsert failures are safely trapped and reported."""
    emb_service = DeterministicEmbeddingService()
    mock_qdrant = MagicMock(spec=QdrantService)
    mock_qdrant.collection_name = "test_col"
    mock_qdrant.ensure_collection.return_value = True
    mock_qdrant.client.upsert.side_effect = ResponseHandlingException(RuntimeError("Qdrant disk quota exceeded"))

    kb_service = KnowledgeBaseService(qdrant_service=mock_qdrant, embedding_service=emb_service)

    docs = [
        PreparedKnowledgeDocument(
            record_type=KnowledgeRecordType.DEFECT,
            source_id="def-2",
            project_id=str(uuid4()),
            title="Broken cart",
            search_text="Cart calculation error",
        )
    ]

    res = kb_service.index_documents(docs)
    assert res.is_successful is False
    assert res.total_indexed == 0
    assert res.total_failed == 1
    assert len(res.errors) == 1
    assert "Qdrant upsert failure" in res.errors[0].error


def test_knowledge_index_api_endpoint(client: TestClient, db_session: Session) -> None:
    """Verify POST /projects/{project_id}/knowledge/index endpoint triggers indexing."""
    project = Project(id=uuid4(), name="API Test Project")
    db_session.add(project)
    req = Requirement(id=uuid4(), project_id=project.id, title="API Req", description="Desc")
    db_session.add(req)
    tc = TestCase(
        id=uuid4(),
        requirement_id=req.id,
        title="TC 1",
        expected_result="Success",
        test_type=TestType.WEB,
        steps=[],
    )
    db_session.add(tc)
    db_session.commit()

    # Trigger indexing endpoint
    response = client.post(
        f"/api/v1/projects/{project.id}/knowledge/index",
        json={"record_types": ["test_case"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_discovered" in data
    assert "total_indexed" in data
    assert "total_failed" in data
    assert "is_successful" in data
    assert data["total_discovered"] >= 1
