import hashlib
import math
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import ResponseHandlingException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.enums import TestType
from app.schemas.knowledge import (
    KnowledgeRecordType,
    PreparedKnowledgeDocument,
)
from app.services.embedding_service import EmbeddingGenerationError, EmbeddingService
from app.services.knowledge_base_service import KnowledgeBaseService, generate_point_id
from app.services.knowledge_retrieval_service import (
    KnowledgeRetrievalError,
    KnowledgeRetrievalService,
)
from app.services.qdrant_service import QdrantOperatingMode, QdrantService


class DeterministicRetrievalEmbeddingService(EmbeddingService):
    """
    Deterministic embedding test double producing normalized 384-d vectors without model downloads.
    Identical strings have cosine similarity 1.0; different strings produce distinct similarity scores.
    """

    def __init__(self) -> None:
        pass

    def embed_text(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec = [float((b % 100) - 50) for b in h]
        while len(vec) < 384:
            vec.extend(vec[: min(len(vec), 384 - len(vec))])
        vec = vec[:384]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


@pytest.fixture
def memory_qdrant() -> QdrantService:
    settings = Settings(
        qdrant_mode="memory",
        qdrant_collection=f"test_retrieval_{uuid4().hex[:8]}",
        qdrant_vector_size=384,
    )
    svc = QdrantService(settings=settings, mode=QdrantOperatingMode.MEMORY)
    yield svc
    svc.close()


def test_query_embedding_and_retrieval_flow(memory_qdrant: QdrantService) -> None:
    """Verify semantic search embeds query, queries Qdrant, and returns structured candidates."""
    emb_service = DeterministicRetrievalEmbeddingService()
    kb_service = KnowledgeBaseService(qdrant_service=memory_qdrant, embedding_service=emb_service)
    retrieval_service = KnowledgeRetrievalService(qdrant_service=memory_qdrant, embedding_service=emb_service)

    proj_id = str(uuid4())
    doc = PreparedKnowledgeDocument(
        record_type=KnowledgeRecordType.DEFECT,
        source_id="def-101",
        project_id=proj_id,
        title="Checkout button unresponsive",
        search_text="Checkout button unresponsive on mobile viewport during payment flow",
        is_verified_resolution=True,
        metadata={"severity": "critical", "component": "checkout"},
    )
    kb_service.index_documents([doc])

    # Search with identical text -> high cosine similarity ~1.0
    res = retrieval_service.search_project_knowledge(
        project_id=proj_id,
        query="Checkout button unresponsive on mobile viewport during payment flow",
        min_score=0.5,
    )

    assert res.total_found == 1
    candidate = res.candidates[0]
    assert candidate.record_type == KnowledgeRecordType.DEFECT
    assert candidate.source_id == "def-101"
    assert candidate.project_id == proj_id
    assert candidate.title == "Checkout button unresponsive"
    assert candidate.is_verified_resolution is True
    assert candidate.similarity_score > 0.99
    assert candidate.metadata.get("severity") == "critical"


def test_mandatory_project_scoped_filtering(memory_qdrant: QdrantService) -> None:
    """Verify tenant isolation: queries for Project A never return points from Project B."""
    emb_service = DeterministicRetrievalEmbeddingService()
    kb_service = KnowledgeBaseService(qdrant_service=memory_qdrant, embedding_service=emb_service)
    retrieval_service = KnowledgeRetrievalService(qdrant_service=memory_qdrant, embedding_service=emb_service)

    proj_a = str(uuid4())
    proj_b = str(uuid4())
    shared_query = "Database connection pool exhaustion under heavy load"

    # Index same text in Project A and Project B
    doc_a = PreparedKnowledgeDocument(
        record_type=KnowledgeRecordType.FAILURE_ANALYSIS,
        source_id="analysis-a",
        project_id=proj_a,
        title="Analysis Alpha",
        search_text=shared_query,
    )
    doc_b = PreparedKnowledgeDocument(
        record_type=KnowledgeRecordType.FAILURE_ANALYSIS,
        source_id="analysis-b",
        project_id=proj_b,
        title="Analysis Beta",
        search_text=shared_query,
    )
    kb_service.index_documents([doc_a, doc_b])

    # Search strictly scoped to Project A
    res_a = retrieval_service.search_project_knowledge(
        project_id=proj_a,
        query=shared_query,
    )
    assert res_a.total_found == 1
    assert res_a.candidates[0].source_id == "analysis-a"
    assert res_a.candidates[0].project_id == proj_a

    # Search strictly scoped to Project B
    res_b = retrieval_service.search_project_knowledge(
        project_id=proj_b,
        query=shared_query,
    )
    assert res_b.total_found == 1
    assert res_b.candidates[0].source_id == "analysis-b"
    assert res_b.candidates[0].project_id == proj_b

    # Search for non-existent Project C
    proj_c = str(uuid4())
    res_c = retrieval_service.search_project_knowledge(
        project_id=proj_c,
        query=shared_query,
    )
    assert res_c.total_found == 0


def test_record_type_filtering(memory_qdrant: QdrantService) -> None:
    """Verify that filtering by specific record_types excludes other knowledge types."""
    emb_service = DeterministicRetrievalEmbeddingService()
    kb_service = KnowledgeBaseService(qdrant_service=memory_qdrant, embedding_service=emb_service)
    retrieval_service = KnowledgeRetrievalService(qdrant_service=memory_qdrant, embedding_service=emb_service)

    proj_id = str(uuid4())
    shared_text = "API gateway 502 Bad Gateway timeout"

    doc_defect = PreparedKnowledgeDocument(
        record_type=KnowledgeRecordType.DEFECT,
        source_id="def-1",
        project_id=proj_id,
        title="Defect gateway",
        search_text=shared_text,
    )
    doc_tc = PreparedKnowledgeDocument(
        record_type=KnowledgeRecordType.TEST_CASE,
        source_id="tc-1",
        project_id=proj_id,
        title="Test case gateway",
        search_text=shared_text,
    )
    kb_service.index_documents([doc_defect, doc_tc])

    # Search only for defects
    res_defect_only = retrieval_service.search_project_knowledge(
        project_id=proj_id,
        query=shared_text,
        record_types=[KnowledgeRecordType.DEFECT],
    )
    assert res_defect_only.total_found == 1
    assert res_defect_only.candidates[0].record_type == KnowledgeRecordType.DEFECT

    # Search only for test cases
    res_tc_only = retrieval_service.search_project_knowledge(
        project_id=proj_id,
        query=shared_text,
        record_types=[KnowledgeRecordType.TEST_CASE],
    )
    assert res_tc_only.total_found == 1
    assert res_tc_only.candidates[0].record_type == KnowledgeRecordType.TEST_CASE


def test_similarity_threshold_filtering(memory_qdrant: QdrantService) -> None:
    """Verify that results below the similarity threshold are filtered out."""
    emb_service = DeterministicRetrievalEmbeddingService()
    kb_service = KnowledgeBaseService(qdrant_service=memory_qdrant, embedding_service=emb_service)
    retrieval_service = KnowledgeRetrievalService(qdrant_service=memory_qdrant, embedding_service=emb_service)

    proj_id = str(uuid4())
    doc = PreparedKnowledgeDocument(
        record_type=KnowledgeRecordType.DEFECT,
        source_id="def-xyz",
        project_id=proj_id,
        title="Authentication CSRF token validation",
        search_text="Authentication CSRF token validation missing in POST header",
    )
    kb_service.index_documents([doc])

    # Search with completely unrelated query with high threshold
    res_filtered = retrieval_service.search_project_knowledge(
        project_id=proj_id,
        query="CSS layout distortion on tablet viewport grid",
        min_score=0.8,
    )
    # Cosine similarity between unrelated texts is far below 0.8 -> should return 0 candidates
    assert res_filtered.total_found == 0


def test_result_limit_and_ranking(memory_qdrant: QdrantService) -> None:
    """Verify that candidates are bounded by limit and returned in descending score order."""
    emb_service = DeterministicRetrievalEmbeddingService()
    kb_service = KnowledgeBaseService(qdrant_service=memory_qdrant, embedding_service=emb_service)
    retrieval_service = KnowledgeRetrievalService(qdrant_service=memory_qdrant, embedding_service=emb_service)

    proj_id = str(uuid4())
    docs = [
        PreparedKnowledgeDocument(
            record_type=KnowledgeRecordType.DEFECT,
            source_id=f"def-{i}",
            project_id=proj_id,
            title=f"Defect {i}",
            search_text=f"Payment gateway webhook retry failure variant {i}",
        )
        for i in range(10)
    ]
    kb_service.index_documents(docs)

    res = retrieval_service.search_project_knowledge(
        project_id=proj_id,
        query="Payment gateway webhook retry failure",
        limit=3,
        min_score=0.0,
    )

    assert len(res.candidates) == 3
    # Verify descending score order
    scores = [c.similarity_score for c in res.candidates]
    assert scores == sorted(scores, reverse=True)


def test_deduplication_handling(memory_qdrant: QdrantService) -> None:
    """Verify that candidates sharing the same (record_type, source_id) are deduplicated."""
    emb_service = DeterministicRetrievalEmbeddingService()
    retrieval_service = KnowledgeRetrievalService(qdrant_service=memory_qdrant, embedding_service=emb_service)

    proj_id = str(uuid4())
    # Manually insert two points with different point IDs but same payload source_id
    pt_vec = emb_service.embed_text("Same source content")
    pts = [
        models.PointStruct(
            id=str(uuid4()),
            vector=pt_vec,
            payload={
                "record_type": "defect",
                "source_id": "duplicate-source-id",
                "project_id": proj_id,
                "title": "Dup 1",
                "search_text": "Same source content",
            },
        ),
        models.PointStruct(
            id=str(uuid4()),
            vector=pt_vec,
            payload={
                "record_type": "defect",
                "source_id": "duplicate-source-id",
                "project_id": proj_id,
                "title": "Dup 2",
                "search_text": "Same source content",
            },
        ),
    ]
    memory_qdrant.ensure_collection()
    memory_qdrant.client.upsert(collection_name=memory_qdrant.collection_name, points=pts)

    res = retrieval_service.search_project_knowledge(
        project_id=proj_id,
        query="Same source content",
        limit=5,
        min_score=0.0,
    )
    # Deduplication ensures only 1 candidate is returned for that source record
    assert res.total_found == 1
    assert res.candidates[0].source_id == "duplicate-source-id"


def test_invalid_queries_and_thresholds(memory_qdrant: QdrantService) -> None:
    """Verify validation errors on empty queries, out-of-range thresholds, or invalid limits."""
    retrieval_service = KnowledgeRetrievalService(qdrant_service=memory_qdrant)
    proj_id = str(uuid4())

    with pytest.raises(ValueError, match="must not be empty"):
        retrieval_service.search_project_knowledge(project_id=proj_id, query="")

    with pytest.raises(ValueError, match="must not be empty"):
        retrieval_service.search_project_knowledge(project_id=proj_id, query="   \n\t  ")

    with pytest.raises(ValueError, match="between 1 and 50"):
        retrieval_service.search_project_knowledge(project_id=proj_id, query="test", limit=0)

    with pytest.raises(ValueError, match="between 1 and 50"):
        retrieval_service.search_project_knowledge(project_id=proj_id, query="test", limit=51)

    with pytest.raises(ValueError, match="threshold must be between 0.0 and 1.0"):
        retrieval_service.search_project_knowledge(project_id=proj_id, query="test", min_score=-0.1)

    with pytest.raises(ValueError, match="threshold must be between 0.0 and 1.0"):
        retrieval_service.search_project_knowledge(project_id=proj_id, query="test", min_score=1.5)


def test_embedding_failure_handling(memory_qdrant: QdrantService) -> None:
    """Verify that EmbeddingGenerationError is safely caught and wrapped as KnowledgeRetrievalError."""
    mock_emb = MagicMock(spec=EmbeddingService)
    mock_emb.embed_text.side_effect = EmbeddingGenerationError("Inference worker crash")

    retrieval_service = KnowledgeRetrievalService(qdrant_service=memory_qdrant, embedding_service=mock_emb)

    with pytest.raises(KnowledgeRetrievalError, match="Failed to generate query embedding"):
        retrieval_service.search_project_knowledge(project_id=str(uuid4()), query="Test failure")


def test_qdrant_failure_handling() -> None:
    """Verify that Qdrant search failures are caught and wrapped as KnowledgeRetrievalError."""
    emb_service = DeterministicRetrievalEmbeddingService()
    mock_qdrant = MagicMock(spec=QdrantService)
    mock_qdrant.collection_name = "test_col"
    mock_qdrant.ensure_collection.return_value = True
    mock_qdrant.client.query_points.side_effect = ResponseHandlingException(RuntimeError("Qdrant unreachable"))

    retrieval_service = KnowledgeRetrievalService(qdrant_service=mock_qdrant, embedding_service=emb_service)

    with pytest.raises(KnowledgeRetrievalError, match="Vector search execution failure"):
        retrieval_service.search_project_knowledge(project_id=str(uuid4()), query="Test failure")


def test_api_knowledge_search_endpoint(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify POST /api/v1/projects/{project_id}/knowledge/search endpoint."""
    # Seed project in PostgreSQL
    project = Project(id=uuid4(), name="Search API Project")
    db_session.add(project)
    req = Requirement(id=uuid4(), project_id=project.id, title="Search Req", description="Desc")
    db_session.add(req)
    tc = TestCase(
        id=uuid4(),
        requirement_id=req.id,
        title="Search TestCase",
        expected_result="200 OK",
        test_type=TestType.WEB,
        steps=[],
    )
    db_session.add(tc)
    db_session.commit()

    # Index test document into a memory Qdrant
    settings = Settings(
        qdrant_mode="memory",
        qdrant_collection=f"test_api_{uuid4().hex[:8]}",
        qdrant_vector_size=384,
    )
    qdrant = QdrantService(settings=settings, mode=QdrantOperatingMode.MEMORY)
    emb_service = DeterministicRetrievalEmbeddingService()
    kb_service = KnowledgeBaseService(db=db_session, qdrant_service=qdrant, embedding_service=emb_service)
    doc = PreparedKnowledgeDocument(
        record_type=KnowledgeRecordType.TEST_CASE,
        source_id=str(tc.id),
        project_id=str(project.id),
        title="Search TestCase",
        search_text="Search TestCase 200 OK",
    )
    kb_service.index_documents([doc])

    # Monkeypatch KnowledgeRetrievalService in routes to use this configured instance
    retrieval_instance = KnowledgeRetrievalService(
        db=db_session,
        qdrant_service=qdrant,
        embedding_service=emb_service,
    )
    monkeypatch.setattr(
        "app.api.routes.knowledge.KnowledgeRetrievalService",
        lambda db: retrieval_instance,
    )

    response = client.post(
        f"/api/v1/projects/{project.id}/knowledge/search",
        json={
            "query": "Search TestCase 200 OK",
            "limit": 5,
            "min_score": 0.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "Search TestCase 200 OK"
    assert data["total_found"] >= 1
    assert len(data["candidates"]) >= 1
    cand = data["candidates"][0]
    assert cand["record_type"] == "test_case"
    assert cand["project_id"] == str(project.id)
    assert "similarity_score" in cand
