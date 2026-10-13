import hashlib
import json
from pathlib import Path
import re
from typing import Any
import urllib.parse
from uuid import UUID

from app.core.config import Settings, get_settings
from app.models.enums import EvidenceType
from app.testing.contract import EvidencePayload

SENSITIVE_KEYS = {
    "authorization",
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "api_key",
    "apikey",
    "api-key",
    "access_token",
    "refresh_token",
    "cookie",
    "session",
    "private_key",
    "credential",
    "credentials",
    "auth",
}

SENSITIVE_QUERY_PARAMS = {
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "api-key",
    "key",
    "secret",
    "password",
    "passwd",
    "pwd",
    "credential",
    "credentials",
    "auth",
    "signature",
    "sig",
}


def is_sensitive_param(param_name: str) -> bool:
    """Check if a query parameter name indicates sensitive credential data."""
    norm = str(param_name).lower().replace("-", "_")
    if norm in SENSITIVE_QUERY_PARAMS:
        return True
    for variant in ("token", "key", "secret", "password", "credential", "auth"):
        if norm.endswith(f"_{variant}") or norm.startswith(f"{variant}_"):
            return True
    return False


def sanitize_url_string(url_str: str) -> str:
    """Redacts sensitive query parameter values and basic-auth credentials from a URL string."""
    if not isinstance(url_str, str) or not url_str.strip():
        return url_str

    try:
        parsed = urllib.parse.urlsplit(url_str)
        has_query = bool(parsed.query)
        has_userinfo = "@" in parsed.netloc

        if not has_query and not has_userinfo:
            return url_str

        # Redact basic-auth password in netloc if present
        new_netloc = parsed.netloc
        if has_userinfo:
            userinfo, host = parsed.netloc.split("@", 1)
            if ":" in userinfo:
                username, _ = userinfo.split(":", 1)
                new_netloc = f"{username}:[REDACTED]@{host}"
            else:
                new_netloc = f"[REDACTED]@{host}"

        # Redact sensitive query parameters while preserving nonsensitive ones
        new_query = parsed.query
        if has_query:
            query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            sanitized_pairs = []
            for k, v in query_pairs:
                if is_sensitive_param(k):
                    sanitized_pairs.append((k, "[REDACTED]"))
                else:
                    sanitized_pairs.append((k, v))
            new_query = urllib.parse.urlencode(sanitized_pairs, safe="[]:")

        return urllib.parse.urlunsplit(
            (parsed.scheme, new_netloc, parsed.path, new_query, parsed.fragment)
        )
    except Exception:
        return re.sub(
            r'(?i)([\?&](?:token|access_token|refresh_token|api_key|apikey|api-key|key|secret|password|credential)=)[^&\s#]+',
            r'\1[REDACTED]',
            url_str,
        )


def sanitize_log_text(log_text: str) -> str:
    """Redacts authorization headers, bearer tokens, embedded sensitive URLs, and credentials from log text."""
    if not isinstance(log_text, str) or not log_text:
        return log_text

    text = log_text

    # 1. Redact Authorization headers
    text = re.sub(
        r'(?i)(authorization\s*:\s*(?:bearer|basic|token)?\s*)[A-Za-z0-9_\-\.\+/=]+',
        r'\1[REDACTED]',
        text,
    )

    # 2. Redact standalone Bearer tokens e.g. "Bearer eyJhbGciOi..."
    text = re.sub(
        r'(?i)\b(bearer\s+)[A-Za-z0-9_\-\.\+/=]+',
        r'\1[REDACTED]',
        text,
    )

    # 3. Redact Basic auth tokens e.g. "Basic dXNlcjpwYXNz..."
    text = re.sub(
        r'(?i)\b(basic\s+)[A-Za-z0-9\+/=]{8,}',
        r'\1[REDACTED]',
        text,
    )

    # 4. Redact key-value credential patterns e.g. "api_key=secret", "password: 'xyz'", "token: abc"
    text = re.sub(
        r'(?i)\b(api_key|apikey|api-key|access_token|refresh_token|token|secret|password|passwd|private_key|credential)(\s*[:=]\s*)[\'"]?([^\s\'"&;,\n\r]+)[\'"]?',
        r'\1\2[REDACTED]',
        text,
    )

    # 5. Redact embedded URLs with query params
    def _url_match_sub(match: re.Match) -> str:
        url_match = match.group(0)
        return sanitize_url_string(url_match)

    text = re.sub(
        r'https?://[^\s\'"<>]+',
        _url_match_sub,
        text,
    )

    return text


def sanitize_sensitive_data(value: Any) -> Any:
    """Recursively redacts credential keys, tokens, and sensitive URL query parameters from data dictionaries and lists."""
    if isinstance(value, dict):
        sanitized = {}
        for k, v in value.items():
            k_lower = str(k).lower().replace("-", "_")
            if any(s in k_lower for s in SENSITIVE_KEYS):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_sensitive_data(v)
        return sanitized
    elif isinstance(value, list):
        return [sanitize_sensitive_data(item) for item in value]
    elif isinstance(value, str):
        if ("?" in value and ("/" in value or "http" in value)) or ("@" in value and "://" in value):
            return sanitize_url_string(value)
        if re.search(r'(?i)\b(bearer|basic)\s+[A-Za-z0-9_\-\.\+/=]+', value):
            return sanitize_log_text(value)
        return value
    return value


class EvidenceManager:
    """Manages physical storage, metadata creation, checksums, and secret redaction for execution evidence."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_dir = Path(self.settings.evidence_storage_dir).resolve()
        self.screenshots_dir = self.base_dir / "screenshots"
        self.logs_dir = self.base_dir / "logs"
        self.requests_dir = self.base_dir / "requests"

        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.requests_dir.mkdir(parents=True, exist_ok=True)

    def _safe_write(self, target_dir: Path, filename: str, data: bytes) -> Path:
        """Write file ensuring path containment inside evidence directory."""
        filepath = (target_dir / filename).resolve()
        if not filepath.is_relative_to(self.base_dir):
            raise ValueError("Security violation: path traversal detected in evidence storage path.")
        filepath.write_bytes(data)
        return filepath

    def save_screenshot(
        self,
        execution_id: UUID,
        step_index: int,
        image_bytes: bytes,
        label: str | None = None,
        metadata: dict | None = None,
    ) -> EvidencePayload:
        filename = f"{execution_id}_step_{step_index}.png"
        self._safe_write(self.screenshots_dir, filename, image_bytes)
        sha256 = hashlib.sha256(image_bytes).hexdigest()

        relative_uri = f"screenshots/{filename}"
        safe_meta = sanitize_sensitive_data(metadata or {})
        return EvidencePayload(
            evidence_type=EvidenceType.SCREENSHOT,
            uri=relative_uri,
            label=label or f"Screenshot for step {step_index}",
            content_type="image/png",
            metadata={
                "step_index": step_index,
                "file_size_bytes": len(image_bytes),
                "size_bytes": len(image_bytes),
                "sha256": sha256,
                **safe_meta,
            },
        )

    def save_log(
        self,
        execution_id: UUID,
        log_text: str,
        label: str | None = None,
        metadata: dict | None = None,
    ) -> EvidencePayload:
        filename = f"{execution_id}_execution.log"
        cleaned_text = sanitize_log_text(log_text)
        log_bytes = cleaned_text.encode("utf-8")
        self._safe_write(self.logs_dir, filename, log_bytes)
        sha256 = hashlib.sha256(log_bytes).hexdigest()

        relative_uri = f"logs/{filename}"
        safe_meta = sanitize_sensitive_data(metadata or {})
        return EvidencePayload(
            evidence_type=EvidenceType.LOG,
            uri=relative_uri,
            label=label or "Execution log",
            content_type="text/plain",
            metadata={
                "file_size_bytes": len(log_bytes),
                "size_bytes": len(log_bytes),
                "sha256": sha256,
                **safe_meta,
            },
        )

    def save_request_response(
        self,
        execution_id: UUID,
        step_index: int,
        data: dict,
        label: str | None = None,
    ) -> EvidencePayload:
        filename = f"{execution_id}_step_{step_index}_req_res.json"
        sanitized = sanitize_sensitive_data(data)
        content = json.dumps(sanitized, indent=2).encode("utf-8")
        self._safe_write(self.requests_dir, filename, content)
        sha256 = hashlib.sha256(content).hexdigest()

        relative_uri = f"requests/{filename}"
        return EvidencePayload(
            evidence_type=EvidenceType.REQUEST_RESPONSE,
            uri=relative_uri,
            label=label or f"Request/Response for step {step_index}",
            content_type="application/json",
            metadata={
                "step_index": step_index,
                "file_size_bytes": len(content),
                "size_bytes": len(content),
                "sha256": sha256,
            },
        )
