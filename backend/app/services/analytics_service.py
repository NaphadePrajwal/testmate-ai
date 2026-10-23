from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import Date, cast, distinct, func, select
from sqlalchemy.orm import Session

from app.models.defect import Defect
from app.models.enums import DefectStatus, ExecutionStatus, Severity
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.schemas.analytics import (
    ExecutionTrendPoint,
    ProjectAnalyticsResponse,
    ProjectReportResponse,
    ProjectTraceabilityResponse,
    RecentExecutionItem,
    TraceabilityItem,
    TraceabilityTestCaseItem,
)
from app.services.project_service import ProjectService


class AnalyticsService:
    """Service providing aggregate analytics, requirement traceability, and project reporting."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_project_analytics(self, project_id: UUID) -> ProjectAnalyticsResponse:
        project = ProjectService(self.db).get_project(project_id)

        # 1. Total Requirements
        total_requirements = (
            self.db.scalar(
                select(func.count(Requirement.id)).where(Requirement.project_id == project_id)
            )
            or 0
        )

        # 2. Total Test Cases
        total_test_cases = (
            self.db.scalar(
                select(func.count(TestCase.id))
                .join(Requirement, TestCase.requirement_id == Requirement.id)
                .where(Requirement.project_id == project_id)
            )
            or 0
        )

        # 3. Executions by Status
        exec_rows = self.db.execute(
            select(TestExecution.status, func.count(TestExecution.id))
            .join(TestCase, TestExecution.test_case_id == TestCase.id)
            .join(Requirement, TestCase.requirement_id == Requirement.id)
            .where(Requirement.project_id == project_id)
            .group_by(TestExecution.status)
        ).all()

        exec_status_counts: dict[str, int] = {str(r[0]): r[1] for r in exec_rows}
        passed = exec_status_counts.get(ExecutionStatus.PASSED.value, 0)
        failed = exec_status_counts.get(ExecutionStatus.FAILED.value, 0)
        error = exec_status_counts.get(ExecutionStatus.ERROR.value, 0)
        running = exec_status_counts.get(ExecutionStatus.RUNNING.value, 0)
        queued = exec_status_counts.get(ExecutionStatus.QUEUED.value, 0)
        cancelled = exec_status_counts.get(ExecutionStatus.CANCELLED.value, 0)
        total_executions = sum(exec_status_counts.values())

        # Pass Rate: passed / completed (passed + failed + error) * 100
        completed_executions = passed + failed + error
        execution_pass_rate = (
            round((passed / completed_executions * 100), 1) if completed_executions > 0 else 0.0
        )

        # 4. Covered Requirements (linked to >= 1 test case)
        covered_requirements = (
            self.db.scalar(
                select(func.count(distinct(Requirement.id)))
                .join(TestCase, TestCase.requirement_id == Requirement.id)
                .where(Requirement.project_id == project_id)
            )
            or 0
        )
        requirement_coverage_rate = (
            round((covered_requirements / total_requirements * 100), 1)
            if total_requirements > 0
            else 0.0
        )

        # 5. Defects Breakdown
        defect_rows = self.db.execute(
            select(Defect.status, Defect.severity, func.count(Defect.id))
            .join(TestExecution, Defect.execution_id == TestExecution.id)
            .join(TestCase, TestExecution.test_case_id == TestCase.id)
            .join(Requirement, TestCase.requirement_id == Requirement.id)
            .where(Requirement.project_id == project_id)
            .group_by(Defect.status, Defect.severity)
        ).all()

        defects_by_status: dict[str, int] = defaultdict(int)
        defects_by_severity: dict[str, int] = defaultdict(int)
        total_defects = 0
        open_defects = 0

        for status_val, sev_val, count in defect_rows:
            s_str = str(status_val)
            sev_str = str(sev_val)
            defects_by_status[s_str] += count
            defects_by_severity[sev_str] += count
            total_defects += count
            if s_str in (DefectStatus.NEW.value, DefectStatus.TRIAGED.value):
                open_defects += count

        critical_defects = defects_by_severity.get(Severity.CRITICAL.value, 0)
        high_defects = defects_by_severity.get(Severity.HIGH.value, 0)
        medium_defects = defects_by_severity.get(Severity.MEDIUM.value, 0)
        low_defects = defects_by_severity.get(Severity.LOW.value, 0)

        # 6. Execution Trends (Last 14 days)
        today = datetime.now(timezone.utc).date()
        fourteen_days_ago = today - timedelta(days=13)

        trend_rows = self.db.execute(
            select(
                TestExecution.created_at,
                TestExecution.status,
            )
            .join(TestCase, TestExecution.test_case_id == TestCase.id)
            .join(Requirement, TestCase.requirement_id == Requirement.id)
            .where(
                Requirement.project_id == project_id,
                TestExecution.created_at >= fourteen_days_ago,
            )
        ).all()

        date_status_map: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for created_at_val, status_val in trend_rows:
            if created_at_val:
                d_str = (
                    created_at_val.date().isoformat()
                    if hasattr(created_at_val, "date")
                    else str(created_at_val)[:10]
                )
                date_status_map[d_str][str(status_val)] += 1

        execution_trends: list[ExecutionTrendPoint] = []
        for i in range(14):
            day_dt = fourteen_days_ago + timedelta(days=i)
            day_str = day_dt.isoformat()
            day_counts = date_status_map.get(day_str, {})
            p_cnt = day_counts.get(ExecutionStatus.PASSED.value, 0)
            f_cnt = day_counts.get(ExecutionStatus.FAILED.value, 0)
            e_cnt = day_counts.get(ExecutionStatus.ERROR.value, 0)
            tot = sum(day_counts.values())
            execution_trends.append(
                ExecutionTrendPoint(
                    date=day_str,
                    passed=p_cnt,
                    failed=f_cnt,
                    error=e_cnt,
                    total=tot,
                )
            )

        # 7. Recent Executions (Top 5)
        recent_rows = self.db.execute(
            select(
                TestExecution.id,
                TestExecution.test_case_id,
                TestCase.title,
                TestExecution.status,
                TestExecution.executor,
                TestExecution.created_at,
                TestExecution.summary,
            )
            .join(TestCase, TestExecution.test_case_id == TestCase.id)
            .join(Requirement, TestCase.requirement_id == Requirement.id)
            .where(Requirement.project_id == project_id)
            .order_by(TestExecution.created_at.desc())
            .limit(5)
        ).all()

        recent_executions = [
            RecentExecutionItem(
                id=r[0],
                test_case_id=r[1],
                test_case_title=r[2],
                status=str(r[3]),
                executor=r[4],
                duration_ms=(
                    float(r[6].get("duration_ms", 0))
                    if isinstance(r[6], dict) and r[6].get("duration_ms")
                    else None
                ),
                created_at=r[5],
            )
            for r in recent_rows
        ]

        return ProjectAnalyticsResponse(
            project_id=project.id,
            project_name=project.name,
            total_requirements=total_requirements,
            total_test_cases=total_test_cases,
            total_test_executions=total_executions,
            passed_executions=passed,
            failed_executions=failed,
            running_executions=running,
            pending_executions=queued,
            error_executions=error,
            execution_pass_rate=execution_pass_rate,
            requirement_coverage_rate=requirement_coverage_rate,
            total_defects=total_defects,
            open_defects=open_defects,
            critical_defects=critical_defects,
            high_defects=high_defects,
            medium_defects=medium_defects,
            low_defects=low_defects,
            defects_by_status=dict(defects_by_status),
            defects_by_severity=dict(defects_by_severity),
            execution_trends=execution_trends,
            recent_executions=recent_executions,
        )

    def get_project_traceability(self, project_id: UUID) -> ProjectTraceabilityResponse:
        ProjectService(self.db).get_project(project_id)

        # Fetch all requirements
        requirements = list(
            self.db.scalars(
                select(Requirement)
                .where(Requirement.project_id == project_id)
                .order_by(Requirement.created_at.desc())
            )
        )

        traceability_items: list[TraceabilityItem] = []
        covered_count = 0

        for req in requirements:
            # Fetch linked test cases
            test_cases = list(
                self.db.scalars(
                    select(TestCase)
                    .where(TestCase.requirement_id == req.id)
                    .order_by(TestCase.created_at.asc())
                )
            )

            tc_items: list[TraceabilityTestCaseItem] = []
            req_latest_status: str | None = None
            defect_count = 0

            for tc in test_cases:
                # Latest execution for this test case
                latest_exec = self.db.scalar(
                    select(TestExecution)
                    .where(TestExecution.test_case_id == tc.id)
                    .order_by(TestExecution.created_at.desc())
                    .limit(1)
                )

                latest_st = str(latest_exec.status) if latest_exec else None
                if latest_st and req_latest_status is None:
                    req_latest_status = latest_st

                # Count defects linked to this test case
                tc_defects = (
                    self.db.scalar(
                        select(func.count(Defect.id))
                        .join(TestExecution, Defect.execution_id == TestExecution.id)
                        .where(TestExecution.test_case_id == tc.id)
                    )
                    or 0
                )
                defect_count += tc_defects

                tc_items.append(
                    TraceabilityTestCaseItem(
                        id=tc.id,
                        title=tc.title,
                        test_type=str(tc.test_type),
                        review_status=str(tc.review_status),
                        status=str(tc.status),
                        latest_execution_status=latest_st,
                    )
                )

            is_covered = len(test_cases) > 0
            if is_covered:
                covered_count += 1

            traceability_items.append(
                TraceabilityItem(
                    requirement_id=req.id,
                    requirement_title=req.title,
                    requirement_status=str(req.status),
                    test_cases_count=len(test_cases),
                    coverage_status="covered" if is_covered else "uncovered",
                    latest_execution_status=req_latest_status,
                    test_cases=tc_items,
                    defect_count=defect_count,
                )
            )

        total_reqs = len(requirements)
        uncovered_count = total_reqs - covered_count
        coverage_rate = (
            round((covered_count / total_reqs * 100), 1) if total_reqs > 0 else 0.0
        )

        # Orphaned statistics
        # Cases without executions
        cases_without_executions = (
            self.db.scalar(
                select(func.count(TestCase.id))
                .join(Requirement, TestCase.requirement_id == Requirement.id)
                .outerjoin(TestExecution, TestExecution.test_case_id == TestCase.id)
                .where(Requirement.project_id == project_id, TestExecution.id.is_(None))
            )
            or 0
        )

        return ProjectTraceabilityResponse(
            project_id=project_id,
            total_requirements=total_reqs,
            covered_requirements=covered_count,
            uncovered_requirements=uncovered_count,
            coverage_rate=coverage_rate,
            requirements_without_cases=uncovered_count,
            cases_without_executions=cases_without_executions,
            items=traceability_items,
        )

    def get_project_report(self, project_id: UUID) -> ProjectReportResponse:
        project = ProjectService(self.db).get_project(project_id)
        analytics = self.get_project_analytics(project_id)
        traceability = self.get_project_traceability(project_id)

        # Balanced quality score calculation (0 - 100):
        # 40% Pass Rate + 40% Requirement Coverage - 5% per open critical/high defect penalty (min 0)
        base_score = (analytics.execution_pass_rate * 0.4) + (analytics.requirement_coverage_rate * 0.4)
        defect_penalty = (analytics.critical_defects * 10) + (analytics.high_defects * 5)
        quality_score = max(0.0, min(100.0, round(base_score - defect_penalty, 1)))

        return ProjectReportResponse(
            project_id=project.id,
            project_name=project.name,
            project_description=project.description,
            created_at=project.created_at,
            analytics=analytics,
            traceability_summary=traceability,
            quality_score=quality_score,
        )
