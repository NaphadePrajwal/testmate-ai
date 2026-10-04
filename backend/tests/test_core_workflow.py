from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.defect import Defect
from app.models.enums import DefectStatus, EvidenceType, ExecutionStatus, Severity
from app.models.execution_evidence import ExecutionEvidence
from app.models.project import Project
from app.models.test_execution import TestExecution
from app.services.project_service import ProjectService


def create_project(client: TestClient, name: str) -> dict[str, object]:
    response = client.post("/api/v1/projects", json={"name": name, "description": "Project description"})
    assert response.status_code == 201, response.text
    return response.json()


def create_requirement(client: TestClient, project_id: str, title: str = "Login requirement") -> dict[str, object]:
    response = client.post(
        f"/api/v1/projects/{project_id}/requirements",
        json={"title": title, "description": "Users can sign in.", "acceptance_criteria": ["Valid user can sign in."]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_test_case(client: TestClient, project_id: str, requirement_id: str) -> dict[str, object]:
    response = client.post(
        f"/api/v1/projects/{project_id}/test-cases",
        json={
            "requirement_id": requirement_id,
            "title": "Valid sign-in",
            "expected_result": "Dashboard is displayed.",
            "test_type": "web",
            "steps": [{"action": "Submit valid credentials", "expected_result": "Dashboard is displayed."}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_project_requirement_and_test_case_crud_with_pagination(client: TestClient) -> None:
    project = create_project(client, "Core workflow")
    project_id = str(project["id"])
    requirement = create_requirement(client, project_id)
    test_case = create_test_case(client, project_id, str(requirement["id"]))

    listed = client.get(f"/api/v1/projects/{project_id}/test-cases?limit=1&offset=0")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == test_case["id"]

    updated = client.patch(f"/api/v1/projects/{project_id}/test-cases/{test_case['id']}", json={"priority": "high"})
    assert updated.status_code == 200
    assert updated.json()["priority"] == "high"
    assert updated.json()["version"] == 2

    requirement_update = client.patch(
        f"/api/v1/projects/{project_id}/requirements/{requirement['id']}", json={"status": "approved"}
    )
    assert requirement_update.status_code == 200
    assert requirement_update.json()["title"] == "Login requirement"
    assert requirement_update.json()["status"] == "approved"

    requirements = client.get(f"/api/v1/projects/{project_id}/requirements?status=approved")
    assert requirements.status_code == 200
    assert requirements.json()["total"] == 1


def test_project_list_preserves_phase_zero_database_unavailable_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(_: ProjectService, __: int, ___: int) -> tuple[list[Project], int]:
        raise IntegrityError("SELECT", {}, Exception("database unavailable"))

    monkeypatch.setattr(ProjectService, "list_projects", unavailable)
    response = client.get("/api/v1/projects")

    assert response.status_code == 503
    assert response.json() == {"detail": "Project data is temporarily unavailable."}


def test_invalid_relationships_validation_and_unreferenced_deletes(client: TestClient) -> None:
    project = create_project(client, "Validation project")
    other_project = create_project(client, "Other validation project")
    project_id = str(project["id"])
    requirement = create_requirement(client, project_id, "Disposable requirement")

    invalid_case = client.post(
        f"/api/v1/projects/{other_project['id']}/test-cases",
        json={
            "requirement_id": requirement["id"],
            "title": "Incorrect project case",
            "expected_result": "Never created.",
            "test_type": "web",
        },
    )
    assert invalid_case.status_code == 404
    assert invalid_case.json()["detail"] == "Requirement not found for this project."

    invalid_payload = client.post(f"/api/v1/projects/{project_id}/requirements", json={"title": "Only a title"})
    assert invalid_payload.status_code == 422

    assert client.delete(f"/api/v1/projects/{project_id}/requirements/{requirement['id']}").status_code == 204
    assert client.delete(f"/api/v1/projects/{project_id}").status_code == 204


def test_cross_project_access_and_referenced_deletion_are_rejected(client: TestClient) -> None:
    first_project = create_project(client, "First project")
    second_project = create_project(client, "Second project")
    first_id, second_id = str(first_project["id"]), str(second_project["id"])
    requirement = create_requirement(client, first_id)
    create_test_case(client, first_id, str(requirement["id"]))

    assert client.get(f"/api/v1/projects/{second_id}/requirements/{requirement['id']}").status_code == 404
    assert client.delete(f"/api/v1/projects/{first_id}/requirements/{requirement['id']}").status_code == 409
    assert client.delete(f"/api/v1/projects/{first_id}").status_code == 409


def test_database_constraints_preserve_traceability(client: TestClient, db_session: Session) -> None:
    project = create_project(client, "Constrained project")
    project_id = str(project["id"])
    requirement = create_requirement(client, project_id, "Unique requirement")

    duplicate = client.post(
        f"/api/v1/projects/{project_id}/requirements",
        json={"title": "Unique requirement", "description": "Duplicate title."},
    )
    assert duplicate.status_code == 409

    with pytest.raises(IntegrityError):
        db_session.execute(delete(Project).where(Project.id == UUID(project_id)))
        db_session.flush()
    db_session.rollback()


def test_execution_artifacts_are_project_scoped_and_lock_test_case(client: TestClient, db_session: Session) -> None:
    project = create_project(client, "Execution history")
    other_project = create_project(client, "Other execution history")
    project_id = str(project["id"])
    requirement = create_requirement(client, project_id)
    test_case = create_test_case(client, project_id, str(requirement["id"]))

    execution = TestExecution(
        test_case_id=UUID(str(test_case["id"])),
        status=ExecutionStatus.FAILED,
        summary={"duration_ms": 140},
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(execution)
    db_session.commit()
    evidence = ExecutionEvidence(
        execution_id=execution.id,
        evidence_type=EvidenceType.LOG,
        uri="test://execution.log",
        metadata_={"line_count": 4},
    )
    defect = Defect(
        execution_id=execution.id,
        title="Sign-in failure",
        description="The dashboard did not load.",
        severity=Severity.HIGH,
        status=DefectStatus.NEW,
    )
    db_session.add_all([evidence, defect])
    db_session.commit()

    assert client.get(f"/api/v1/projects/{project_id}/executions/{execution.id}").status_code == 200
    evidence_response = client.get(f"/api/v1/projects/{project_id}/executions/{execution.id}/evidence")
    assert evidence_response.status_code == 200
    assert evidence_response.json()["items"][0]["metadata"] == {"line_count": 4}
    assert client.get(f"/api/v1/projects/{project_id}/defects/{defect.id}").status_code == 200
    assert client.get(f"/api/v1/projects/{other_project['id']}/executions/{execution.id}").status_code == 404

    assert client.patch(f"/api/v1/projects/{project_id}/test-cases/{test_case['id']}", json={"priority": "low"}).status_code == 409
    assert client.delete(f"/api/v1/projects/{project_id}/test-cases/{test_case['id']}").status_code == 409
