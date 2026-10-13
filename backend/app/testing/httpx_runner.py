from datetime import datetime, timezone
import json
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx

from app.core.config import Settings, get_settings
from app.models.enums import ExecutionStatus
from app.models.test_case import TestCase
from app.testing.contract import ExecutionOutcome, StepExecutionResult
from app.testing.evidence_manager import EvidenceManager, sanitize_log_text, sanitize_url_string


BLOCKED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "instance-data",
}


class HttpxApiRunner:
    """Deterministic, SSRF-guarded HTTP API test execution adapter."""

    def __init__(self, settings: Settings | None = None, evidence_manager: EvidenceManager | None = None) -> None:
        self.settings = settings or get_settings()
        self.evidence_manager = evidence_manager or EvidenceManager(self.settings)

    def _validate_target_url(self, url: str) -> str:
        """Resolve and validate target URL against allowed hosts and SSRF blocklist."""
        # If relative, join with target_api_url
        if url.startswith("/"):
            base = self.settings.target_api_url.rstrip("/")
            full_url = f"{base}{url}"
        elif not url.startswith("http://") and not url.startswith("https://"):
            base = self.settings.target_api_url.rstrip("/")
            full_url = f"{base}/{url}"
        else:
            full_url = url

        parsed = urlparse(full_url)
        hostname = (parsed.hostname or "").lower()

        if hostname in BLOCKED_HOSTS:
            raise ValueError(f"Security error: target host '{hostname}' is blocked to prevent SSRF.")

        allowed = self.settings.allowed_api_hosts
        if allowed and "*" not in allowed:
            if hostname not in allowed:
                raise ValueError(
                    f"Security error: target host '{hostname}' is not in approved hosts ({', '.join(allowed)})."
                )

        return full_url

    def _parse_step(self, step: dict[str, Any]) -> tuple[str, str, dict[str, Any], int | None]:
        """Extract HTTP method, URL, payload, and expected status code from step and data."""
        data = step.get("data") or {}
        action = step.get("action", "").strip()
        expected_result = step.get("expected_result") or ""

        method = (data.get("method") or "").upper()
        url = data.get("url") or data.get("path") or ""
        payload = data.get("payload") or data.get("json") or data.get("body") or None
        expected_status = data.get("expected_status") or data.get("status_code")

        # Fallback to parsing text if not structured
        if not method or not url:
            method_match = re.search(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b", action, re.IGNORECASE)
            if method_match:
                method = method_match.group(1).upper()
            else:
                method = "GET"

            url_match = re.search(r"(/[\w\-/.]+|(?:https?://[^\s\"']+))", action)
            if url_match:
                url = url_match.group(1)
            else:
                url = "/"

        if expected_status is None:
            # Try to find 3-digit status code in expected_result or action
            code_match = re.search(r"\b([1-5]\d{2})\b", f"{expected_result} {action}")
            if code_match:
                expected_status = int(code_match.group(1))
            else:
                expected_status = 200

        return method, url, payload, int(expected_status)

    def execute(self, test_case: TestCase, execution_id: UUID) -> ExecutionOutcome:
        """Execute all steps of an API test case sequentially."""
        started_at = datetime.now(timezone.utc)
        step_results: list[StepExecutionResult] = []
        overall_status = ExecutionStatus.PASSED
        first_error_message: str | None = None
        evidence_items = []

        steps = test_case.steps or []
        if not steps:
            # Single baseline step from expected_result/preconditions if steps is empty
            steps = [{"action": f"Verify {test_case.title}", "expected_result": test_case.expected_result, "data": {}}]

        with httpx.Client(timeout=self.settings.http_timeout_seconds) as client:
            for idx, raw_step in enumerate(steps, start=1):
                step_start = time.perf_counter()
                action_text = raw_step.get("action", f"Step {idx}")
                expected_text = raw_step.get("expected_result") or "Status matches expectation"
                
                try:
                    method, url_str, payload, expected_status = self._parse_step(raw_step)
                    target_url = self._validate_target_url(url_str)

                    # Prepare and send request
                    req_kwargs: dict[str, Any] = {}
                    if payload is not None:
                        if isinstance(payload, (dict, list)):
                            req_kwargs["json"] = payload
                        else:
                            req_kwargs["content"] = str(payload)

                    response = client.request(method, target_url, **req_kwargs)
                    step_duration = (time.perf_counter() - step_start) * 1000

                    # Parse response body
                    res_body: Any = None
                    try:
                        res_body = response.json()
                    except Exception:
                        res_body = response.text[:2000]

                    # Record Request/Response evidence
                    evidence_data = {
                        "request": {
                            "method": method,
                            "url": target_url,
                            "headers": dict(response.request.headers),
                            "body": payload,
                        },
                        "response": {
                            "status_code": response.status_code,
                            "headers": dict(response.headers),
                            "body": res_body,
                        },
                    }
                    evidence_payload = self.evidence_manager.save_request_response(
                        execution_id=execution_id,
                        step_index=idx,
                        data=evidence_data,
                    )
                    evidence_items.append(evidence_payload)

                    # Validate assertions
                    actual_summary = f"HTTP {response.status_code} {response.reason_phrase}"
                    if response.status_code == expected_status:
                        step_status = "passed"
                        err_msg = None
                    else:
                        step_status = "failed"
                        overall_status = ExecutionStatus.FAILED
                        err_msg = f"Expected HTTP {expected_status}, but received HTTP {response.status_code}"
                        if not first_error_message:
                            first_error_message = err_msg

                    step_results.append(
                        StepExecutionResult(
                            step_index=idx,
                            action=sanitize_url_string(f"{method} {url_str}"),
                            status=step_status,
                            expected=f"HTTP {expected_status}",
                            actual=actual_summary,
                            duration_ms=round(step_duration, 2),
                            error_message=sanitize_log_text(err_msg) if err_msg else None,
                            details={"status_code": response.status_code, "target_url": sanitize_url_string(target_url)},
                        )
                    )

                except Exception as exc:
                    step_duration = (time.perf_counter() - step_start) * 1000
                    overall_status = ExecutionStatus.ERROR
                    err_msg = sanitize_log_text(str(exc))
                    if not first_error_message:
                        first_error_message = err_msg

                    step_results.append(
                        StepExecutionResult(
                            step_index=idx,
                            action=sanitize_url_string(action_text),
                            status="error",
                            expected=expected_text,
                            actual="Execution encountered error",
                            duration_ms=round(step_duration, 2),
                            error_message=err_msg,
                            details={
                                "exception": type(exc).__name__,
                                "target_url": sanitize_url_string(target_url) if "target_url" in locals() else None,
                            },
                        )
                    )
                    break

        completed_at = datetime.now(timezone.utc)
        return ExecutionOutcome(
            status=overall_status,
            step_results=step_results,
            error_message=first_error_message,
            evidence_items=evidence_items,
            started_at=started_at,
            completed_at=completed_at,
        )
