import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import SessionLocal
from app.models.defect import Defect
from app.models.enums import TestCaseStatus
from app.models.execution_failure_analysis import ExecutionFailureAnalysis
from app.models.knowledge_indexing_job import (
    IndexingJobAction,
    IndexingJobStatus,
    KnowledgeIndexingJob,
)
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.schemas.knowledge import KnowledgeRecordType
from app.services.database import commit_or_rollback
from app.services.knowledge_base_service import KnowledgeBaseService

logger = logging.getLogger(__name__)


class KnowledgeIndexingJobService:
    """
    Manages durable outbox jobs for asynchronous, idempotent vector knowledge indexing.
    Guarantees that index mutations (upserts and deletes) are captured in PostgreSQL
    and processed reliably even when vector infrastructure experiences transient failures.
    """

    def __init__(
        self,
        db: Session | None = None,
        knowledge_base_service: KnowledgeBaseService | None = None,
    ) -> None:
        self.db = db
        self.kb_service = knowledge_base_service

    @contextmanager
    def _get_session(self) -> Generator[Session, None, None]:
        """Provide a safe database session, creating a fresh scoped session if needed."""
        if self.db is not None and self.db.is_active:
            yield self.db
        else:
            session = SessionLocal()
            try:
                yield session
            finally:
                session.close()

    def enqueue_job(
        self,
        project_id: UUID,
        record_type: KnowledgeRecordType | str,
        source_id: UUID,
        action: IndexingJobAction | str = IndexingJobAction.UPSERT,
    ) -> KnowledgeIndexingJob:
        """
        Idempotently enqueue an indexing job.
        If a pending or failed job exists for this exact record, reuses and resets it
        to prevent uncontrolled job queue proliferation.
        """
        rec_type_str = record_type.value if hasattr(record_type, "value") else str(record_type)
        act_enum = action if isinstance(action, IndexingJobAction) else IndexingJobAction(action)

        with self._get_session() as session:
            # Check for existing pending or failed job for same target
            existing_job = session.scalar(
                select(KnowledgeIndexingJob)
                .where(
                    KnowledgeIndexingJob.project_id == project_id,
                    KnowledgeIndexingJob.record_type == rec_type_str,
                    KnowledgeIndexingJob.source_id == source_id,
                    KnowledgeIndexingJob.status.in_([IndexingJobStatus.PENDING, IndexingJobStatus.FAILED]),
                )
                .limit(1)
            )

            if existing_job is not None:
                existing_job.action = act_enum
                existing_job.status = IndexingJobStatus.PENDING
                existing_job.retry_count = 0
                existing_job.last_error = None
                existing_job.updated_at = datetime.now(timezone.utc)
                commit_or_rollback(session)
                logger.info(
                    "Re-queued existing indexing job %s for %s (%s) action=%s.",
                    existing_job.id,
                    rec_type_str,
                    source_id,
                    act_enum.value,
                )
                return existing_job

            # Create new job
            new_job = KnowledgeIndexingJob(
                project_id=project_id,
                record_type=rec_type_str,
                source_id=source_id,
                action=act_enum,
                status=IndexingJobStatus.PENDING,
                retry_count=0,
                max_retries=3,
            )
            session.add(new_job)
            commit_or_rollback(session)
            session.refresh(new_job)
            logger.info(
                "Enqueued new indexing job %s for project %s: %s (%s) action=%s.",
                new_job.id,
                project_id,
                rec_type_str,
                source_id,
                act_enum.value,
            )
            return new_job

    def process_job(self, job_id: UUID) -> bool:
        """
        Process a single indexing job with transactional safety and error bounding.
        Returns True if indexing succeeded or job was already completed; False otherwise.
        """
        with self._get_session() as session:
            job = session.get(KnowledgeIndexingJob, job_id)
            if job is None:
                logger.warning("Indexing job %s not found.", job_id)
                return False

            if job.status == IndexingJobStatus.COMPLETED:
                return True

            job.status = IndexingJobStatus.PROCESSING
            job.updated_at = datetime.now(timezone.utc)
            commit_or_rollback(session)

            kb = self.kb_service or KnowledgeBaseService(db=session)

            try:
                if job.action == IndexingJobAction.DELETE:
                    kb.delete_point(job.record_type, str(job.source_id))
                elif job.action == IndexingJobAction.UPSERT:
                    self._dispatch_upsert(session, kb, job)

                # Successful completion
                job.status = IndexingJobStatus.COMPLETED
                job.completed_at = datetime.now(timezone.utc)
                job.last_error = None
                job.updated_at = datetime.now(timezone.utc)
                commit_or_rollback(session)
                logger.info(
                    "Indexing job %s completed successfully for %s (%s).",
                    job.id,
                    job.record_type,
                    job.source_id,
                )
                return True

            except Exception as exc:
                job.retry_count += 1
                job.last_error = str(exc)
                job.updated_at = datetime.now(timezone.utc)
                if job.retry_count >= job.max_retries:
                    job.status = IndexingJobStatus.FAILED
                else:
                    job.status = IndexingJobStatus.PENDING

                commit_or_rollback(session)
                logger.warning(
                    "Indexing job %s failed (attempt %d/%d): %s",
                    job.id,
                    job.retry_count,
                    job.max_retries,
                    exc,
                )
                return False

    def _dispatch_upsert(self, session: Session, kb: KnowledgeBaseService, job: KnowledgeIndexingJob) -> None:
        """Resolve and upsert a record according to its record_type."""
        if job.record_type == KnowledgeRecordType.DEFECT.value:
            defect = session.scalar(
                select(Defect)
                .where(Defect.id == job.source_id)
                .options(
                    selectinload(Defect.execution)
                    .selectinload(TestExecution.test_case)
                    .selectinload(TestCase.requirement)
                )
            )
            if defect is None:
                # Source record deleted from database: delete from vector index
                kb.delete_point(job.record_type, str(job.source_id))
            else:
                kb.index_single_defect(defect, project_id=job.project_id)

        elif job.record_type == KnowledgeRecordType.FAILURE_ANALYSIS.value:
            analysis = session.scalar(
                select(ExecutionFailureAnalysis).where(ExecutionFailureAnalysis.id == job.source_id)
            )
            if analysis is None:
                kb.delete_point(job.record_type, str(job.source_id))
            else:
                kb.index_single_failure_analysis(analysis, project_id=job.project_id)

        elif job.record_type == KnowledgeRecordType.TEST_CASE.value:
            test_case = session.scalar(
                select(TestCase)
                .where(TestCase.id == job.source_id)
                .options(selectinload(TestCase.requirement))
            )
            if test_case is None or test_case.status == TestCaseStatus.RETIRED:
                kb.delete_point(job.record_type, str(job.source_id))
            else:
                kb.index_single_test_case(test_case, project_id=job.project_id)

        else:
            raise ValueError(f"Unsupported record_type for knowledge indexing: {job.record_type}")

    def process_project_jobs(
        self,
        project_id: UUID,
        limit: int = 50,
        include_failed: bool = True,
    ) -> tuple[int, int]:
        """
        Process pending or failed indexing jobs for a project.
        Returns a tuple of (successful_count, failed_count).
        """
        statuses = [IndexingJobStatus.PENDING]
        if include_failed:
            statuses.append(IndexingJobStatus.FAILED)

        with self._get_session() as session:
            jobs = list(
                session.scalars(
                    select(KnowledgeIndexingJob)
                    .where(
                        KnowledgeIndexingJob.project_id == project_id,
                        KnowledgeIndexingJob.status.in_(statuses),
                    )
                    .order_by(KnowledgeIndexingJob.created_at.asc())
                    .limit(limit)
                )
            )
            job_ids = [j.id for j in jobs]

        success_count = 0
        failed_count = 0
        for j_id in job_ids:
            if self.process_job(j_id):
                success_count += 1
            else:
                failed_count += 1

        return success_count, failed_count

    def list_jobs(
        self,
        project_id: UUID,
        status: IndexingJobStatus | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[KnowledgeIndexingJob], int, int, int]:
        """
        List indexing jobs for a project with counts.
        Returns (items, total, pending_count, failed_count).
        """
        with self._get_session() as session:
            base_stmt = select(KnowledgeIndexingJob).where(KnowledgeIndexingJob.project_id == project_id)

            total = session.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
            pending_count = (
                session.scalar(
                    select(func.count()).select_from(
                        base_stmt.where(KnowledgeIndexingJob.status == IndexingJobStatus.PENDING).subquery()
                    )
                )
                or 0
            )
            failed_count = (
                session.scalar(
                    select(func.count()).select_from(
                        base_stmt.where(KnowledgeIndexingJob.status == IndexingJobStatus.FAILED).subquery()
                    )
                )
                or 0
            )

            query = base_stmt
            if status is not None:
                stat_val = status.value if hasattr(status, "value") else str(status)
                query = query.where(KnowledgeIndexingJob.status == stat_val)

            items = list(
                session.scalars(
                    query.order_by(KnowledgeIndexingJob.created_at.desc()).offset(offset).limit(limit)
                )
            )
            return items, total, pending_count, failed_count
