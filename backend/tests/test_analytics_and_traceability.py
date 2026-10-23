from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.defect import Defect
from app.models.enums import DefectStatus, ExecutionStatus, Priority, ReviewStatus, Severity, TestCaseStatus, TestType
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution


def test_analytics_empty_project(client: TestClient, db_session: Session) -> None:
    """Verifies that an empty project returns zero counts without division by zero errors."""
    project = Project(name=f"Empty Analytics Project {uuid4().hex[:6]}", description="No data")
    db_session.add(project)
    db_session.commit()

    resp = client.get(f"/api/v1/projects/{project.id}/analytics")
    assert resp.status_code == 200
    data = resp.json()

    assert data["project_id"] == str(project.id)
    assert data["total_requirements"] == 0
    assert data["total_test_cases"] == 0
    assert data["total_test_executions"] == 0
    assert data["execution_pass_rate"] == 0.0
    assert data["requirement_coverage_rate"] == 0.0
    assert data["total_defects"] == 0
    assert data["open_defects"] == 0
    assert len(data["execution_trends"]) == 14
    assert len(data["recent_executions"]) == 0


def test_analytics_and_traceability_metrics(client: TestClient, db_session: Session) -> None:
    """Verifies accurate metric aggregation across requirements, test cases, executions, and defects."""
    project = Project(name=f"Analytics Project {uuid4().hex[:6]}")
    db_session.add(project)
    db_session.commit()

    # Requirement 1: Covered (has test cases)
    req1 = Requirement(
        project_id=project.id,
        title="User Authentication",
        description="Login and logout capabilities",
        acceptance_criteria=["Valid login", "Invalid login error"],
    )
    # Requirement 2: Uncovered (no test cases)
    req2 = Requirement(
        project_id=project.id,
        title="Password Reset",
        description="Reset via email token",
        acceptance_criteria=["Email delivered"],
    )
    db_session.add_all([req1, req2])
    db_session.commit()

    # Test cases for Requirement 1
    tc1 = TestCase(
        requirement_id=req1.id,
        title="Valid Credentials Login",
        description="Logs in with valid credentials",
        expected_result="User dashboard displayed",
        test_type=TestType.WEB,
        priority=Priority.HIGH,
        review_status=ReviewStatus.APPROVED,
        status=TestCaseStatus.APPROVED,
    )
    tc2 = TestCase(
        requirement_id=req1.id,
        title="Invalid Password Login",
        description="Shows error with bad password",
        expected_result="Error banner displayed",
        test_type=TestType.WEB,
        priority=Priority.MEDIUM,
        review_status=ReviewStatus.APPROVED,
        status=TestCaseStatus.APPROVED,
    )
    db_session.add_all([tc1, tc2])
    db_session.commit()

    # Executions: 1 passed on tc1, 1 failed on tc2
    exec1 = TestExecution(
        test_case_id=tc1.id,
        status=ExecutionStatus.PASSED,
        summary={"total_steps": 2, "passed_steps": 2, "failed_steps": 0, "duration_ms": 1200},
    )
    exec2 = TestExecution(
        test_case_id=tc2.id,
        status=ExecutionStatus.FAILED,
        summary={"total_steps": 2, "passed_steps": 1, "failed_steps": 1, "duration_ms": 2500},
    )
    db_session.add_all([exec1, exec2])
    db_session.commit()

    # Defect originating from failed execution
    defect = Defect(
        execution_id=exec2.id,
        title="Incorrect error message on invalid password",
        description="Expected 'Invalid credentials', observed blank screen",
        severity=Severity.HIGH,
        status=DefectStatus.NEW,
    )
    db_session.add(defect)
    db_session.commit()

    # 1. Verify Analytics
    analytics_resp = client.get(f"/api/v1/projects/{project.id}/analytics")
    assert analytics_resp.status_code == 200
    a_data = analytics_resp.json()

    assert a_data["total_requirements"] == 2
    assert a_data["total_test_cases"] == 2
    assert a_data["total_test_executions"] == 2
    assert a_data["passed_executions"] == 1
    assert a_data["failed_executions"] == 1
    # 1 passed out of 2 completed => 50.0%
    assert a_data["execution_pass_rate"] == 50.0
    # 1 covered out of 2 total requirements => 50.0%
    assert a_data["requirement_coverage_rate"] == 50.0
    assert a_data["total_defects"] == 1
    assert a_data["open_defects"] == 1
    assert a_data["high_defects"] == 1
    assert len(a_data["recent_executions"]) == 2

    # 2. Verify Traceability
    trace_resp = client.get(f"/api/v1/projects/{project.id}/traceability")
    assert trace_resp.status_code == 200
    t_data = trace_resp.json()

    assert t_data["total_requirements"] == 2
    assert t_data["covered_requirements"] == 1
    assert t_data["uncovered_requirements"] == 1
    assert t_data["coverage_rate"] == 50.0
    assert t_data["requirements_without_cases"] == 1
    assert t_data["cases_without_executions"] == 0
    assert len(t_data["items"]) == 2

    # 3. Verify Project Report
    report_resp = client.get(f"/api/v1/projects/{project.id}/report")
    assert report_resp.status_code == 200
    r_data = report_resp.json()

    assert r_data["project_name"] == project.name
    assert r_data["analytics"]["execution_pass_rate"] == 50.0
    assert r_data["quality_score"] > 0


def test_analytics_cross_project_isolation(client: TestClient, db_session: Session) -> None:
    """Verifies that project metrics are strictly isolated and never cross-pollinate."""
    proj1 = Project(name=f"Project Alpha {uuid4().hex[:6]}")
    proj2 = Project(name=f"Project Beta {uuid4().hex[:6]}")
    db_session.add_all([proj1, proj2])
    db_session.commit()

    # Add requirements and cases only to Project 1
    req1 = Requirement(project_id=proj1.id, title="Alpha Feature", description="Alpha only")
    db_session.add(req1)
    db_session.commit()

    tc1 = TestCase(
        requirement_id=req1.id,
        title="Alpha Case",
        description="Testing alpha",
        expected_result="Alpha expected result",
        test_type=TestType.WEB,
        status=TestCaseStatus.APPROVED,
    )
    db_session.add(tc1)
    db_session.commit()

    # Project 1 should reflect its counts
    res1 = client.get(f"/api/v1/projects/{proj1.id}/analytics").json()
    assert res1["total_requirements"] == 1
    assert res1["total_test_cases"] == 1

    # Project 2 must have zero counts
    res2 = client.get(f"/api/v1/projects/{proj2.id}/analytics").json()
    assert res2["total_requirements"] == 0
    assert res2["total_test_cases"] == 0


def test_analytics_non_existent_project(client: TestClient) -> None:
    """Verifies that requests for an unknown project return 404."""
    unknown_id = uuid4()
    resp = client.get(f"/api/v1/projects/{unknown_id}/analytics")
    assert resp.status_code == 404
