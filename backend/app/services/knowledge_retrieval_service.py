import logging
from typing import Any
from uuid import UUID

from qdrant_client.http import models
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.schemas.knowledge import (
    HistoricalCandidateItem,
    KnowledgeRecordType,
    KnowledgeSearchResponse,
)
from app.services.embedding_service import EmbeddingGenerationError, EmbeddingService
from app.services.project_service import ProjectService
from app.services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)


class KnowledgeRetrievalError(Exception):
    """Raised when semantic retrieval fails due to external vector service or embedding errors."""


class KnowledgeRetrievalService:
    """
    Orchestrates semantic vector retrieval across historical QA intelligence in Qdrant.
    Enforces project-scoped tenant isolation at query time, applies score thresholds,
    filters by record types, and returns structured historical candidates.
    """

    def __init__(
        self,
        db: Session | None = None,
        qdrant_service: QdrantService | None = None,
        embedding_service: EmbeddingService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.qdrant_service = qdrant_service or QdrantService(settings=self.settings)
        self.embedding_service = embedding_service or EmbeddingService(settings=self.settings)

    def search_project_knowledge(
        self,
        project_id: UUID | str,
        query: str,
        record_types: list[KnowledgeRecordType] | None = None,
        limit: int | None = None,
        min_score: float | None = None,
    ) -> KnowledgeSearchResponse:
        """
        Retrieve relevant historical candidates (defects, failure analyses, test cases)
        from Qdrant using semantic cosine similarity, strictly scoped to project_id.

        Parameters:
            project_id: Authoritative project UUID identifying the tenant.
            query: Free-text search query (error trace, failure description, question).
            record_types: Optional subset of KnowledgeRecordType to search.
            limit: Maximum number of candidates to return (1-50).
            min_score: Minimum cosine similarity score threshold (0.0 to 1.0).

        Returns:
            KnowledgeSearchResponse containing ranked candidates.
        """
        # 1. Validate query
        if not query or not query.strip():
            raise ValueError("Search query must not be empty or whitespace-only.")
        clean_query = query.strip()
        if len(clean_query) > 5000:
            clean_query = clean_query[:5000]

        # 2. Validate project
        if self.db is not None:
            # Enforce that the project exists in PostgreSQL
            proj_uuid = UUID(str(project_id))
            ProjectService(self.db).get_project(proj_uuid)
        proj_id_str = str(project_id).strip().lower()

        # 3. Validate limit and threshold
        effective_limit = limit if limit is not None else self.settings.knowledge_retrieval_limit
        if effective_limit < 1 or effective_limit > 50:
            raise ValueError("Result limit must be between 1 and 50.")

        effective_min_score = (
            min_score if min_score is not None else self.settings.knowledge_retrieval_min_score
        )
        if effective_min_score < 0.0 or effective_min_score > 1.0:
            raise ValueError("Similarity score threshold must be between 0.0 and 1.0.")

        # 4. Ensure Qdrant collection is available before embedding
        try:
            self.qdrant_service.ensure_collection()
        except Exception as exc:
            logger.error("Qdrant collection check failed: %s", exc)
            raise KnowledgeRetrievalError(f"Vector search execution failure: {exc}") from exc

        # 5. Generate query embedding
        try:
            query_vector = self.embedding_service.embed_text(clean_query)
        except EmbeddingGenerationError as exc:
            logger.error("Embedding generation failure during semantic retrieval: %s", exc)
            raise KnowledgeRetrievalError(f"Failed to generate query embedding: {exc}") from exc
        except Exception as exc:
            logger.error("Unexpected embedding failure: %s", exc)
            raise KnowledgeRetrievalError(f"Embedding pipeline error: {exc}") from exc

        # 6. Build Qdrant filter - Mandatory project_id isolation
        must_conditions: list[models.FieldCondition] = [
            models.FieldCondition(
                key="project_id",
                match=models.MatchValue(value=proj_id_str),
            )
        ]

        # Optional record-type filter
        if record_types:
            type_vals = [
                rt.value if isinstance(rt, KnowledgeRecordType) else str(rt)
                for rt in record_types
            ]
            must_conditions.append(
                models.FieldCondition(
                    key="record_type",
                    match=models.MatchAny(any=type_vals),
                )
            )

        query_filter = models.Filter(must=must_conditions)

        # 7. Execute Qdrant vector search
        try:
            # Fetch a slight surplus (up to limit * 2) to accommodate potential deduplication
            fetch_limit = min(50, effective_limit * 2)

            response = self.qdrant_service.client.query_points(
                collection_name=self.qdrant_service.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=fetch_limit,
                score_threshold=effective_min_score,
                with_payload=True,
            )
            scored_points = response.points or []
        except Exception as exc:
            logger.error("Qdrant query_points failed for project '%s': %s", proj_id_str, exc)
            raise KnowledgeRetrievalError(f"Vector search execution failure: {exc}") from exc

        # 7. Process, deduplicate, and assemble candidate items
        candidates: list[HistoricalCandidateItem] = []
        seen_records: set[tuple[str, str]] = set()

        # Standard payload keys to exclude from custom metadata dict
        standard_keys = {
            "record_type",
            "source_id",
            "project_id",
            "title",
            "search_text",
            "is_verified_resolution",
            "created_at",
        }

        for pt in scored_points:
            score = float(pt.score)
            if score < effective_min_score:
                continue

            payload = pt.payload or {}
            raw_record_type = payload.get("record_type")
            source_id = str(payload.get("source_id", pt.id))

            # Deduplication by (record_type, source_id)
            dedup_key = (str(raw_record_type), source_id)
            if dedup_key in seen_records:
                continue
            seen_records.add(dedup_key)

            try:
                rec_type = KnowledgeRecordType(raw_record_type)
            except (ValueError, TypeError):
                rec_type = KnowledgeRecordType.DEFECT

            extra_metadata: dict[str, Any] = {
                k: v for k, v in payload.items() if k not in standard_keys
            }

            candidate = HistoricalCandidateItem(
                record_type=rec_type,
                source_id=source_id,
                project_id=str(payload.get("project_id", proj_id_str)),
                title=str(payload.get("title", "Historical Candidate")),
                search_text=str(payload.get("search_text", "")),
                similarity_score=round(score, 4),
                is_verified_resolution=bool(payload.get("is_verified_resolution", False)),
                metadata=extra_metadata,
            )
            candidates.append(candidate)

            if len(candidates) >= effective_limit:
                break

        return KnowledgeSearchResponse(
            query=clean_query,
            total_found=len(candidates),
            candidates=candidates,
        )
