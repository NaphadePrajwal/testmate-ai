import json
from pathlib import Path
from uuid import UUID

from app.core.config import Settings, get_settings
from app.models.enums import EvidenceType
from app.testing.contract import EvidencePayload


class EvidenceManager:
    """Manages physical storage and metadata creation for execution evidence."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_dir = Path(self.settings.evidence_storage_dir).resolve()
        self.screenshots_dir = self.base_dir / "screenshots"
        self.logs_dir = self.base_dir / "logs"
        self.requests_dir = self.base_dir / "requests"

        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.requests_dir.mkdir(parents=True, exist_ok=True)

    def save_screenshot(
        self,
        execution_id: UUID,
        step_index: int,
        image_bytes: bytes,
        label: str | None = None,
        metadata: dict | None = None,
    ) -> EvidencePayload:
        filename = f"{execution_id}_step_{step_index}.png"
        filepath = self.screenshots_dir / filename
        filepath.write_bytes(image_bytes)

        relative_uri = f"screenshots/{filename}"
        return EvidencePayload(
            evidence_type=EvidenceType.SCREENSHOT,
            uri=relative_uri,
            label=label or f"Screenshot for step {step_index}",
            content_type="image/png",
            metadata={"step_index": step_index, "file_size_bytes": len(image_bytes), **(metadata or {})},
        )

    def save_log(
        self,
        execution_id: UUID,
        log_text: str,
        label: str | None = None,
        metadata: dict | None = None,
    ) -> EvidencePayload:
        filename = f"{execution_id}_execution.log"
        filepath = self.logs_dir / filename
        filepath.write_text(log_text, encoding="utf-8")

        relative_uri = f"logs/{filename}"
        return EvidencePayload(
            evidence_type=EvidenceType.LOG,
            uri=relative_uri,
            label=label or "Execution log",
            content_type="text/plain",
            metadata={"file_size_bytes": len(log_text.encode("utf-8")), **(metadata or {})},
        )

    def save_request_response(
        self,
        execution_id: UUID,
        step_index: int,
        data: dict,
        label: str | None = None,
    ) -> EvidencePayload:
        filename = f"{execution_id}_step_{step_index}_req_res.json"
        filepath = self.requests_dir / filename
        content = json.dumps(data, indent=2)
        filepath.write_text(content, encoding="utf-8")

        relative_uri = f"requests/{filename}"
        return EvidencePayload(
            evidence_type=EvidenceType.REQUEST_RESPONSE,
            uri=relative_uri,
            label=label or f"Request/Response for step {step_index}",
            content_type="application/json",
            metadata={"step_index": step_index, "file_size_bytes": len(content.encode("utf-8"))},
        )
