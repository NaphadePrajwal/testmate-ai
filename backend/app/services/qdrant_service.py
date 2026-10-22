import logging
import threading
from enum import StrEnum
from typing import Any, ClassVar

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class QdrantOperatingMode(StrEnum):
    """Supported operating modes for Qdrant vector database."""

    SERVER = "server"
    LOCAL = "local"
    MEMORY = "memory"


class QdrantService:
    """
    Manages vector storage connectivity, lifecycle, collection initialization,
    and health diagnostics for TestMate AI's historical bug intelligence.
    """

    _shared_clients: ClassVar[dict[str, QdrantClient]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(
        self,
        settings: Settings | None = None,
        client: QdrantClient | None = None,
        mode: QdrantOperatingMode | str | None = None,
    ) -> None:
        self.settings = settings or get_settings()

        raw_mode = str(mode or self.settings.qdrant_mode).lower().strip()
        try:
            self.mode = QdrantOperatingMode(raw_mode)
        except ValueError:
            valid_modes = [m.value for m in QdrantOperatingMode]
            raise ValueError(
                f"Invalid Qdrant operating mode: '{raw_mode}'. Must be one of: {valid_modes}"
            )

        self.collection_name = self.settings.qdrant_collection
        self.vector_size = self.settings.qdrant_vector_size
        self._client = client
        self._owns_client = client is None

    def _cache_key(self) -> str:
        if self.mode == QdrantOperatingMode.LOCAL:
            return f"local:{self.settings.qdrant_local_path}"
        elif self.mode == QdrantOperatingMode.SERVER:
            return f"server:{self.settings.qdrant_url}"
        return f"memory:{id(self)}"

    @classmethod
    def reset_shared_clients(cls) -> None:
        """Close and reset any shared QdrantClient instances."""
        with cls._lock:
            for client in cls._shared_clients.values():
                try:
                    client.close()
                except Exception:
                    pass
            cls._shared_clients.clear()

    @property
    def client(self) -> QdrantClient:
        """Lazily initialize and return the QdrantClient matching exactly one operating mode."""
        if self._client is None:
            if self.mode != QdrantOperatingMode.MEMORY:
                key = self._cache_key()
                with self._lock:
                    if key in self._shared_clients:
                        self._client = self._shared_clients[key]
                        self._owns_client = False
                    else:
                        self._client = self._create_client()
                        self._shared_clients[key] = self._client
            else:
                self._client = self._create_client()
        return self._client

    def _create_client(self) -> QdrantClient:
        """
        Instantiate QdrantClient for the selected mode.
        Ensures that exactly one operating mode is used (never mixing server and local path).
        """
        if self.mode == QdrantOperatingMode.SERVER:
            logger.info("Initializing Qdrant client in SERVER mode (url=%s)", self.settings.qdrant_url)
            return QdrantClient(
                url=self.settings.qdrant_url,
                api_key=self.settings.qdrant_api_key or None,
                timeout=self.settings.qdrant_timeout_seconds,
                check_compatibility=False,
            )
        elif self.mode == QdrantOperatingMode.LOCAL:
            logger.info("Initializing Qdrant client in LOCAL storage mode (path=%s)", self.settings.qdrant_local_path)
            return QdrantClient(path=self.settings.qdrant_local_path)
        elif self.mode == QdrantOperatingMode.MEMORY:
            logger.info("Initializing Qdrant client in MEMORY mode")
            return QdrantClient(location=":memory:")
        else:
            raise ValueError(f"Unsupported operating mode: {self.mode}")

    def ensure_collection(self) -> bool:
        """
        Idempotently ensure the configured collection exists with 384-d Cosine vectors.
        Returns True if collection exists or was successfully created.
        Safe to call repeatedly without recreating or modifying existing data.
        """
        client = self.client
        try:
            if client.collection_exists(self.collection_name):
                logger.info("Qdrant collection '%s' already exists; skipping creation.", self.collection_name)
                return True

            logger.info(
                "Creating Qdrant collection '%s' (vector_size=%d, distance=COSINE)...",
                self.collection_name,
                self.vector_size,
            )
            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            try:
                client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="project_id",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception as index_exc:
                logger.debug("Payload index creation note: %s", index_exc)

            logger.info("Successfully created Qdrant collection '%s'.", self.collection_name)
            return True
        except Exception as exc:
            logger.warning(
                "Failed to initialize Qdrant collection '%s' (%s mode): %s",
                self.collection_name,
                self.mode.value,
                exc,
            )
            raise

    def get_health(self) -> dict[str, Any]:
        """
        Perform a lightweight connectivity probe.
        Returns a dictionary distinguishing a healthy vector database from an unavailable one,
        without throwing unhandled exceptions.
        """
        try:
            client = self.client
            exists = client.collection_exists(self.collection_name)
            return {
                "status": "connected",
                "mode": self.mode.value,
                "collection": self.collection_name,
                "collection_exists": exists,
            }
        except Exception as exc:
            logger.debug("Qdrant health probe indicated unavailable: %s", exc)
            return {
                "status": "unavailable",
                "mode": self.mode.value,
                "collection": self.collection_name,
                "error": str(exc),
            }

    def is_healthy(self) -> bool:
        """Return True if the vector database is reachable and operational."""
        return self.get_health().get("status") == "connected"

    def close(self) -> None:
        """Close the underlying client connection if owned by this service instance."""
        if self._owns_client and self._client is not None:
            try:
                self._client.close()
            except Exception as exc:
                logger.debug("Error closing Qdrant client: %s", exc)
            finally:
                self._client = None

    def __enter__(self) -> "QdrantService":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
