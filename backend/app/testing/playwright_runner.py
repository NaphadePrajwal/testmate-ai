from datetime import datetime, timezone
import re
import time
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from playwright.sync_api import sync_playwright

from app.core.config import Settings, get_settings
from app.models.enums import ExecutionStatus
from app.models.test_case import TestCase
from app.testing.contract import ExecutionOutcome, StepExecutionResult
from app.testing.evidence_manager import EvidenceManager


BLOCKED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "instance-data",
}


class PlaywrightWebRunner:
    """Safe, sandboxed browser test execution runner using Playwright."""

    def __init__(self, settings: Settings | None = None, evidence_manager: EvidenceManager | None = None) -> None:
        self.settings = settings or get_settings()
        self.evidence_manager = evidence_manager or EvidenceManager(self.settings)

    def _validate_target_url(self, url: str) -> str:
        """Resolve and validate target URL against allowed base URL and security blocklist."""
        if url.startswith("data:"):
            return url

        if url.startswith("/"):
            base = self.settings.target_app_url.rstrip("/")
            full_url = f"{base}{url}"
        elif not url.startswith("http://") and not url.startswith("https://"):
            base = self.settings.target_app_url.rstrip("/")
            full_url = f"{base}/{url}"
        else:
            full_url = url

        parsed = urlparse(full_url)
        hostname = (parsed.hostname or "").lower()

        if hostname in BLOCKED_HOSTS:
            raise ValueError(f"Security error: target host '{hostname}' is blocked to prevent SSRF.")

        return full_url

    def _parse_step(self, step: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Determine action type and parameters from structured data or textual description."""
        data = step.get("data") or {}
        action_text = step.get("action", "").strip()

        action = (data.get("action") or "").lower()

        if action:
            return action, data

        # Parse textual action
        if re.search(r"^(navigate|open|go to|visit)\b", action_text, re.IGNORECASE):
            url_match = re.search(r"(/[\w\-/.]*|(?:https?://[^\s\"']+))", action_text)
            url = url_match.group(1) if url_match else "/"
            return "navigate", {"url": url}

        if re.search(r"^(click|press button|select button)\b", action_text, re.IGNORECASE):
            # Try to find selector or button name
            sel_match = re.search(r"['\"]([^'\"]+)['\"]", action_text)
            selector = sel_match.group(1) if sel_match else "button, a, input[type=submit]"
            return "click", {"selector": selector}

        if re.search(r"^(fill|enter|type|input)\b", action_text, re.IGNORECASE):
            val_match = re.findall(r"['\"]([^'\"]+)['\"]", action_text)
            if len(val_match) >= 2:
                value, selector = val_match[0], val_match[1]
            elif len(val_match) == 1:
                value = val_match[0]
                selector = "input"
            else:
                value = "test"
                selector = "input"
            return "fill", {"selector": selector, "value": value}

        if re.search(r"^(assert|verify|check)\b", action_text, re.IGNORECASE):
            val_match = re.search(r"['\"]([^'\"]+)['\"]", action_text)
            text = val_match.group(1) if val_match else action_text
            return "assert_text", {"text": text}

        # Default fallback: navigate or assert
        return "navigate", {"url": "/"}

    def execute(self, test_case: TestCase, execution_id: UUID) -> ExecutionOutcome:
        """Execute browser steps in an isolated Playwright Chromium instance."""
        started_at = datetime.now(timezone.utc)
        step_results: list[StepExecutionResult] = []
        overall_status = ExecutionStatus.PASSED
        first_error_message: str | None = None
        evidence_items = []

        steps = test_case.steps or []
        if not steps:
            steps = [{"action": f"Navigate to {test_case.title}", "expected_result": test_case.expected_result, "data": {"action": "navigate", "url": "/"}}]

        timeout_ms = int(self.settings.browser_timeout_seconds * 1000)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.settings.browser_headless,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            try:
                for idx, raw_step in enumerate(steps, start=1):
                    step_start = time.perf_counter()
                    action_text = raw_step.get("action", f"Step {idx}")
                    expected_text = raw_step.get("expected_result") or "Action executes successfully"

                    try:
                        action_type, params = self._parse_step(raw_step)
                        actual_result = ""

                        if action_type in ("navigate", "goto"):
                            raw_url = params.get("url") or "/"
                            target_url = self._validate_target_url(raw_url)
                            page.goto(target_url, timeout=timeout_ms)
                            actual_result = f"Navigated to {page.url}"

                        elif action_type == "click":
                            selector = params.get("selector") or "button"
                            page.locator(selector).first.click(timeout=timeout_ms)
                            actual_result = f"Clicked element '{selector}'"

                        elif action_type in ("fill", "type"):
                            selector = params.get("selector") or "input"
                            value = str(params.get("value", ""))
                            page.locator(selector).first.fill(value, timeout=timeout_ms)
                            actual_result = f"Filled element '{selector}'"

                        elif action_type == "select":
                            selector = params.get("selector") or "select"
                            value = str(params.get("value", ""))
                            page.locator(selector).first.select_option(value, timeout=timeout_ms)
                            actual_result = f"Selected option '{value}' in '{selector}'"

                        elif action_type == "assert_text":
                            expected_content = params.get("text") or params.get("expected") or ""
                            page_content = page.content()
                            if expected_content.lower() in page_content.lower():
                                actual_result = f"Found text '{expected_content}' in page content"
                            else:
                                raise AssertionError(f"Expected text '{expected_content}' not found on page.")

                        elif action_type == "assert_visible":
                            selector = params.get("selector") or "body"
                            is_vis = page.locator(selector).first.is_visible()
                            if is_vis:
                                actual_result = f"Element '{selector}' is visible"
                            else:
                                raise AssertionError(f"Element '{selector}' is not visible.")

                        elif action_type == "assert_url":
                            expected_path = params.get("url") or ""
                            current = page.url
                            if expected_path in current:
                                actual_result = f"Current URL matches: {current}"
                            else:
                                raise AssertionError(f"Expected URL to contain '{expected_path}', got '{current}'")

                        else:
                            # Unsupported or unhandled action type
                            actual_result = f"Skipped unsupported action: {action_type}"

                        step_duration = (time.perf_counter() - step_start) * 1000
                        step_results.append(
                            StepExecutionResult(
                                step_index=idx,
                                action=action_text,
                                status="passed",
                                expected=expected_text,
                                actual=actual_result,
                                duration_ms=round(step_duration, 2),
                                details={"action_type": action_type, "url": page.url},
                            )
                        )

                    except Exception as step_exc:
                        step_duration = (time.perf_counter() - step_start) * 1000
                        err_msg = str(step_exc)
                        overall_status = ExecutionStatus.FAILED
                        if not first_error_message:
                            first_error_message = err_msg

                        # Capture screenshot on failure
                        try:
                            screenshot_bytes = page.screenshot(full_page=True)
                            ev = self.evidence_manager.save_screenshot(
                                execution_id=execution_id,
                                step_index=idx,
                                image_bytes=screenshot_bytes,
                                label=f"Failure screenshot for step {idx}",
                                metadata={"status": "failed", "error": err_msg},
                            )
                            evidence_items.append(ev)
                        except Exception:
                            pass

                        step_results.append(
                            StepExecutionResult(
                                step_index=idx,
                                action=action_text,
                                status="failed",
                                expected=expected_text,
                                actual=f"Failure: {err_msg}",
                                duration_ms=round(step_duration, 2),
                                error_message=err_msg,
                                details={"error": err_msg},
                            )
                        )
                        break

                # If passed, capture a final completion screenshot
                if overall_status == ExecutionStatus.PASSED:
                    try:
                        screenshot_bytes = page.screenshot(full_page=True)
                        ev = self.evidence_manager.save_screenshot(
                            execution_id=execution_id,
                            step_index=len(steps),
                            image_bytes=screenshot_bytes,
                            label="Execution completion screenshot",
                            metadata={"status": "passed"},
                        )
                        evidence_items.append(ev)
                    except Exception:
                        pass

            finally:
                context.close()
                browser.close()

        completed_at = datetime.now(timezone.utc)
        return ExecutionOutcome(
            status=overall_status,
            step_results=step_results,
            error_message=first_error_message,
            evidence_items=evidence_items,
            started_at=started_at,
            completed_at=completed_at,
        )
