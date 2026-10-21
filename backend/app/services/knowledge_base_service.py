import logging
import uuid
from typing import Any
from uuid import UUID

from qdrant_client.http import models
from sqlalchemy.orm import Session

from app.models.defect import Defect
from app.models.execution_failure_analysis import ExecutionFailureAnalysis
from app.models.test_case import TestCase
from app.schemas.knowledge import (
    IndexingErrorItem,
    KnowledgeIndexResult,
    KnowledgeRecordType,
    PreparedKnowledgeDocument,
)
from app.services.embedding_service import EmbeddingService
from app.services.knowledge_document_service import KnowledgeDocumentService
from app.services.project_service import ProjectService
from app.services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)

# Stable UUID5 namespace for deterministic Qdrant point IDs
TESTMATE_KNOWLEDGE_NAMESPACE = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6")


def generate_point_id(record_type: KnowledgeRecordType | str, source_id: str) -> str:
    """
    Generate a stable, deterministic UUID5 string for a Qdrant point.
    Ensures that re-indexing the same source record updates the vector point in-place
    rather than accumulating duplicate points.
    """
    type_str = record_type.value if isinstance(record_type, KnowledgeRecordType) else str(record_type)
    key = f"{type_str.strip().lower()}:{str(source_id).strip().lower()}"
    return str(uuid.uuid5(TESTMATE_KNOWLEDGE_NAMESPACE, key))


def _clean_payload_value(val: Any) -> Any:
    """Convert non-JSON-serializable types into serializable representations."""
    if isinstance(val, UUID):
        return str(val)
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if hasattr(val, "value"):
        return val.value
    if isinstance(val, dict):
        return {str(k): _clean_payload_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [_clean_payload_value(x) for x in val]
    return val


class KnowledgeBaseService:
    """
    Orchestrates the ingestion of historical QA knowledge into Qdrant.
    Connects PostgreSQL records -> KnowledgeDocumentService -> EmbeddingService -> QdrantService.
    """

    def __init__(
        self,
        db: Session | None = None,
        qdrant_service: QdrantService | None = None,
        embedding_service: EmbeddingService | None = None,
        document_service: KnowledgeDocumentService | None = None,
    ) -> None:
        self.db = db
        self.qdrant_service = qdrant_service or QdrantService()
        self.embedding_service = embedding_service or EmbeddingService()
        self.document_service = document_service or KnowledgeDocumentService(db=db)

    def build_qdrant_point(
        self,
        doc: PreparedKnowledgeDocument,
        vector: list[float],
    ) -> models.PointStruct:
        """Construct a PointStruct with deterministic ID, vector, and cleaned payload."""
        point_id = generate_point_id(doc.record_type, doc.source_id)

        payload: dict[str, Any] = {
            "record_type": doc.record_type.value,
            "source_id": str(doc.source_id),
            "project_id": str(doc.project_id),
            "title": doc.title,
            "search_text": doc.search_text,
            "is_verified_resolution": doc.is_verified_resolution,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }

        # Merge additional metadata
        for k, v in doc.metadata.items():
            if k not in payload:
                payload[k] = _clean_payload_value(v)

        return models.PointStruct(
            id=point_id,
            vector=vector,
            payload=payload,
        )

    def index_documents(
        self,
        documents: list[PreparedKnowledgeDocument],
        batch_size: int = 32,
    ) -> KnowledgeIndexResult:
        """
        Embed and upsert prepared documents into Qdrant in batches.
        Safe and idempotent: updates existing vectors without creating duplicate points.
        """
        result = KnowledgeIndexResult(
            total_discovered=len(documents),
            total_prepared=len(documents),
        )

        if not documents:
            return result

        # Ensure collection exists before upserting
        try:
            self.qdrant_service.ensure_collection()
        except Exception as exc:
            logger.error("Failed to ensure Qdrant collection: %s", exc)
            result.total_failed = len(documents)
            result.is_successful = False
            result.errors.append(
                IndexingErrorItem(error=f"Vector store collection unavailable: {exc}")
            )
            return result

        # Process in batches
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            batch_texts = [d.search_text for d in batch]

            try:
                vectors = self.embedding_service.embed_batch(batch_texts)
            except Exception as exc:
                logger.error("Failed to generate batch embeddings for %d documents: %s", len(batch), exc)
                result.total_failed += len(batch)
                result.is_successful = False
                for d in batch:
                    result.errors.append(
                        IndexingErrorItem(
                            source_id=d.source_id,
                            record_type=d.record_type.value,
                            error=f"Embedding generation failure: {exc}",
                        )
                    )
                continue

            # Build points
            points: list[models.PointStruct] = []
            for doc, vec in zip(batch, vectors, strict=True):
                points.append(self.build_qdrant_point(doc, vec))

            try:
                self.qdrant_service.client.upsert(
                    collection_name=self.qdrant_service.collection_name,
                    points=points,
                )
                result.total_indexed += len(points)
                logger.info(
                    "Successfully indexed batch of %d points into Qdrant collection '%s'.",
                    len(points),
                    self.qdrant_service.collection_name,
                )
            except Exception as exc:
                logger.error("Qdrant upsert failure for batch of %d points: %s", len(points), exc)
                result.total_failed += len(points)
                result.is_successful = False
                for d in batch:
                    result.errors.append(
                        IndexingErrorItem(
                            source_id=d.source_id,
                            record_type=d.record_type.value,
                            error=f"Qdrant upsert failure: {exc}",
                        )
                    )

        return result

    def index_project_knowledge(
        self,
        project_id: UUID,
        record_types: list[KnowledgeRecordType] | None = None,
        batch_size: int = 32,
    ) -> KnowledgeIndexResult:
        """
        Authoritatively discover and index all historical knowledge records for a project.
        Enforces tenant boundaries via PostgreSQL joins and Qdrant project_id payload tags.
        """
        if self.db is None:
            raise RuntimeError("Database session is required for project knowledge indexing.")

        # Ensure project exists
        ProjectService(self.db).get_project(project_id)

        target_types = set(record_types) if record_types else set(KnowledgeRecordType)
        documents: list[PreparedKnowledgeDocument] = []

        if KnowledgeRecordType.DEFECT in target_types:
            documents.extend(self.document_service.get_preparable_defects(project_id))
        if KnowledgeRecordType.FAILURE_ANALYSIS in target_types:
            documents.extend(self.document_service.get_preparable_failure_analyses(project_id))
        if KnowledgeRecordType.TEST_CASE in target_types:
            documents.extend(self.document_service.get_preparable_test_cases(project_id))

        return self.index_documents(documents, batch_size=batch_size)

    def index_single_defect(self, defect: Defect, project_id: UUID | None = None) -> str:
        """Index or update a single Defect record. Returns the deterministic point ID."""
        doc = self.document_service.prepare_defect(defect, project_id=project_id)
        res = self.index_documents([doc], batch_size=1)
        if not res.is_successful:
            raise RuntimeError(f"Failed to index defect {defect.id}: {res.errors}")
        return generate_point_id(doc.record_type, doc.source_id)

    def index_single_failure_analysis(
        self,
        analysis: ExecutionFailureAnalysis,
        project_id: UUID | None = None,
    ) -> str:
        """Index or update a single ExecutionFailureAnalysis record. Returns the deterministic point ID."""
        doc = self.document_service.prepare_failure_analysis(analysis, project_id=project_id)
        res = self.index_documents([doc], batch_size=1)
        if not res.is_successful:
            raise RuntimeError(f"Failed to index failure analysis {analysis.id}: {res.errors}")
        return generate_point_id(doc.record_type, doc.source_id)

    def index_single_test_case(self, test_case: TestCase, project_id: UUID | None = None) -> str:
        """Index or update a single TestCase record. Returns the deterministic point ID."""
        doc = self.document_service.prepare_test_case(test_case, project_id=project_id)
        res = self.index_documents([doc], batch_size=1)
        if not res.is_successful:
            raise RuntimeError(f"Failed to index test case {test_case.id}: {res.errors}")
        return generate_point_id(doc.record_type, doc.source_id)

    def delete_point(self, record_type: KnowledgeRecordType | str, source_id: str) -> None:
        """Delete a vector point corresponding to a source record ID from Qdrant."""
        point_id = generate_point_id(record_type, source_id)
        try:
            self.qdrant_service.client.delete(
                collection_name=self.qdrant_service.collection_name,
                points_selector=models.PointIdsList(points=[point_id]),
            )
            logger.info("Deleted point '%s' from collection '%s'.", point_id, self.qdrant_service.collection_name)
        except Exception as exc:
            logger.warning("Failed to delete point '%s': %s", point_id, exc)

    def delete_project_knowledge(self, project_id: UUID | str) -> None:
        """Delete all vectors tagged with a project_id from Qdrant."""
        try:
            self.qdrant_service.client.delete(
                collection_name=self.qdrant_service.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="project_id",
                                match=models.MatchValue(value=str(project_id)),
                            )
                        ]
                    )
                ),
            )
            logger.info("Deleted all points for project '%s'.", project_id)
        except Exception as exc:
            logger.warning("Failed to delete points for project '%s': %s", project_id, exc)
