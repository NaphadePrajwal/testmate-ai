import shutil
import tempfile
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import ResponseHandlingException

from app.core.config import Settings
from app.main import app
from app.services.qdrant_service import QdrantOperatingMode, QdrantService


def test_qdrant_mode_validation() -> None:
    """Ensure invalid operating mode raises a clear ValueError."""
    with pytest.raises(ValueError, match="Invalid Qdrant operating mode: 'invalid_mode'"):
        QdrantService(mode="invalid_mode")


def test_in_memory_mode_collection_creation_and_idempotency() -> None:
    """Verify in-memory client creates 384-d Cosine collection and can be called repeatedly safely."""
    settings = Settings(
        qdrant_mode="memory",
        qdrant_collection="test_historical_col",
        qdrant_vector_size=384,
    )
    with QdrantService(settings=settings, mode=QdrantOperatingMode.MEMORY) as service:
        assert service.mode == QdrantOperatingMode.MEMORY
        assert service.is_healthy()

        # Step 1: Initialize collection
        created = service.ensure_collection()
        assert created is True
        assert service.client.collection_exists("test_historical_col")

        # Verify collection configuration
        info = service.client.get_collection("test_historical_col")
        assert info.config.params.vectors.size == 384
        assert info.config.params.vectors.distance == models.Distance.COSINE

        # Step 2: Insert a test vector to ensure repeated initialization does not wipe data
        service.client.upsert(
            collection_name="test_historical_col",
            points=[
                models.PointStruct(
                    id=1,
                    vector=[0.05] * 384,
                    payload={"defect_id": "test-123"},
                )
            ],
        )

        # Step 3: Call ensure_collection again (idempotent repeat call)
        repeated = service.ensure_collection()
        assert repeated is True

        # Existing points must still be intact
        info_after = service.client.get_collection("test_historical_col")
        assert info_after.points_count == 1


def test_local_storage_mode() -> None:
    """Verify local disk directory storage mode initializes and cleans up properly."""
    temp_dir = tempfile.mkdtemp(prefix="testmate_qdrant_")
    try:
        settings = Settings(
            qdrant_mode="local",
            qdrant_local_path=temp_dir,
            qdrant_collection="test_local_col",
            qdrant_vector_size=384,
        )
        service = QdrantService(settings=settings, mode=QdrantOperatingMode.LOCAL)
        assert service.mode == QdrantOperatingMode.LOCAL
        assert service.is_healthy()

        service.ensure_collection()
        assert service.client.collection_exists("test_local_col")
        service.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_server_mode_configuration_and_unavailable_handling() -> None:
    """Verify server mode configuration handles offline server gracefully without crashing."""
    settings = Settings(
        qdrant_mode="server",
        qdrant_url="http://127.0.0.1:65534",  # Non-existent port
        qdrant_timeout_seconds=0.5,
        qdrant_collection="testmate_historical_knowledge",
    )
    service = QdrantService(settings=settings, mode=QdrantOperatingMode.SERVER)
    assert service.mode == QdrantOperatingMode.SERVER

    # Health check must report unavailable rather than raising an unhandled exception
    health = service.get_health()
    assert health["status"] == "unavailable"
    assert health["mode"] == "server"
    assert "error" in health
    assert not service.is_healthy()

    service.close()


def test_qdrant_health_probe_connected() -> None:
    """Verify health reporting on connected in-memory instance."""
    service = QdrantService(mode=QdrantOperatingMode.MEMORY)
    health = service.get_health()
    assert health["status"] == "connected"
    assert health["mode"] == "memory"
    assert "collection_exists" in health
    service.close()


def test_external_client_injection() -> None:
    """Verify an existing QdrantClient instance can be injected (e.g. for mock testing)."""
    mock_client = MagicMock(spec=QdrantClient)
    mock_client.collection_exists.return_value = False

    service = QdrantService(client=mock_client, mode=QdrantOperatingMode.MEMORY)
    assert service.client is mock_client

    service.ensure_collection()
    mock_client.collection_exists.assert_called_once_with(service.collection_name)
    mock_client.create_collection.assert_called_once()


def test_health_api_route_includes_vector_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify /api/v1/health reports vector_database health without breaking existing fields."""
    client = TestClient(app)
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "TestMate AI API"
    assert "database" in data
    assert "vector_database" in data
    assert data["vector_database"]["status"] in ("connected", "unavailable")
