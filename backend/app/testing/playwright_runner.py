from datetime import datetime, timezone
import logging
import re
import time
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from playwright.sync_api import Locator, Page, sync_playwright

from app.core.config import Settings, get_settings
from app.core.url_utils import BLOCKED_HOSTS, is_blocked_host, resolve_navigation_url, validate_and_normalize_url
from app.models.enums import ExecutionStatus
from app.models.test_case import TestCase
from app.testing.contract import ErrorCategory, ExecutionOutcome, StepExecutionResult
from app.testing.evidence_manager import EvidenceManager

logger = logging.getLogger(__name__)


class PlaywrightWebRunner:
    """
    Sandboxed browser test execution runner using Playwright.
    Supports accessible locators (role, label, placeholder, text, test_id),
    structured action sequences, console and network error capture, screenshot evidence,
    and security isolation against SSRF and target abuse.
    """

    def __init__(self, settings: Settings | None = None, evidence_manager: EvidenceManager | None = None) -> None:
        self.settings = settings or get_settings()
        self.evidence_manager = evidence_manager or EvidenceManager(self.settings)

    def _validate_target_url(self, url: str, base_url: str | None = None) -> str:
        """Resolve and validate target URL against allowed base URL and security blocklist."""
        return resolve_navigation_url(url, base_url=base_url)

    def _resolve_locator(self, page: Page, params: dict[str, Any]) -> Locator:
        """
        Resolves an element locator using accessible locators in priority order:
        1. Role and Name (e.g. role="button", name="Submit Payment")
        2. Label (e.g. label="Cardholder Name")
        3. Placeholder (e.g. placeholder="4242...")
        4. Test ID (e.g. test_id="checkout-btn")
        5. Exact or Substring Text
        6. CSS / XPath Selector fallback
        """
        if "role" in params and params["role"]:
            role = str(params["role"]).lower()
            name = params.get("name")
            if name:
                return page.get_by_role(role, name=str(name))
            return page.get_by_role(role)

        if "label" in params and params["label"]:
            return page.get_by_label(str(params["label"]))

        if "placeholder" in params and params["placeholder"]:
            return page.get_by_placeholder(str(params["placeholder"]))

        if "test_id" in params and params["test_id"]:
            return page.get_by_test_id(str(params["test_id"]))

        if "text" in params and params["text"] and params.get("action") not in ("assert_text",):
            return page.get_by_text(str(params["text"]))

        selector = params.get("selector")
        if selector:
            return page.locator(str(selector))

        # Default fallback: general interactive elements
        return page.locator("button, a, input, select, textarea, [role='button']")

    def _parse_step(self, step: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Determine action type and parameters from structured data or textual description."""
        data = step.get("data") or {}
        action_text = step.get("action", "").strip()

        action = (data.get("action") or "").lower().strip()
        if action:
            return action, data

        # 1. Navigation
        if re.search(r"^(navigate|open|go to|visit)\b", action_text, re.IGNORECASE):
            url_match = re.search(r"(/[\w\-/.]*|(?:https?://[^\s\"']+))", action_text)
            url = url_match.group(1) if url_match else "/"
            return "navigate", {"url": url}

        # 2. Click
        if re.search(r"^(click|press|tap)\b", action_text, re.IGNORECASE):
            sel_match = re.search(r"['\"]([^'\"]+)['\"]", action_text)
            target = sel_match.group(1) if sel_match else ""
            if target:
                # If target looks like a CSS selector or ID
                if target.startswith("#") or target.startswith(".") or "[" in target:
                    return "click", {"selector": target}
                # Else check for button/link keyword
                if "button" in action_text.lower():
                    return "click", {"role": "button", "name": target}
                if "link" in action_text.lower():
                    return "click", {"role": "link", "name": target}
                return "click", {"selector": f"text='{target}'", "text": target}
            return "click", {"selector": "button, a, input[type=submit]"}

        # 3. Fill / Enter text
        if re.search(r"^(fill|enter|type|input)\b", action_text, re.IGNORECASE):
            val_match = re.findall(r"['\"]([^'\"]+)['\"]", action_text)
            if len(val_match) >= 2:
                # e.g., Fill 'Cardholder Name' with 'John Doe'
                target_field, val = val_match[0], val_match[1]
                return "fill", {"label": target_field, "placeholder": target_field, "value": val}
            elif len(val_match) == 1:
                val = val_match[0]
                return "fill", {"selector": "input:not([type=hidden])", "value": val}
            return "fill", {"selector": "input", "value": "test"}

        # 4. Select dropdown
        if re.search(r"^(select)\b", action_text, re.IGNORECASE):
            val_match = re.findall(r"['\"]([^'\"]+)['\"]", action_text)
            val = val_match[0] if val_match else "1"
            return "select", {"selector": "select", "value": val}

        # 5. Checkbox check / uncheck
        if re.search(r"^(uncheck)\b", action_text, re.IGNORECASE):
            sel_match = re.search(r"['\"]([^'\"]+)['\"]", action_text)
            label = sel_match.group(1) if sel_match else None
            return "uncheck", {"label": label, "selector": "input[type=checkbox]"}
        if re.search(r"^(check)\b", action_text, re.IGNORECASE):
            sel_match = re.search(r"['\"]([^'\"]+)['\"]", action_text)
            label = sel_match.group(1) if sel_match else None
            return "check", {"label": label, "selector": "input[type=checkbox]"}

        # 6. Assertions
        if re.search(r"\b(title)\b", action_text, re.IGNORECASE):
            val_match = re.search(r"['\"]([^'\"]+)['\"]", action_text)
            expected_title = val_match.group(1) if val_match else action_text
            return "assert_title", {"title": expected_title}

        if re.search(r"\b(url|path)\b", action_text, re.IGNORECASE):
            val_match = re.search(r"['\"]([^'\"]+)['\"]", action_text)
            expected_url = val_match.group(1) if val_match else "/"
            return "assert_url", {"url": expected_url}

        if re.search(r"\b(visible|displayed|shown)\b", action_text, re.IGNORECASE):
            sel_match = re.search(r"['\"]([^'\"]+)['\"]", action_text)
            sel = sel_match.group(1) if sel_match else "body"
            return "assert_visible", {"selector": sel, "text": sel}

        if re.search(r"^(assert|verify|check)\b", action_text, re.IGNORECASE):
            val_match = re.search(r"['\"]([^'\"]+)['\"]", action_text)
            text = val_match.group(1) if val_match else action_text
            return "assert_text", {"text": text}

        # 7. Wait
        if re.search(r"^(wait)\b", action_text, re.IGNORECASE):
            num_match = re.search(r"(\d+)\s*(?:ms|seconds?|s)?", action_text)
            ms = int(num_match.group(1)) * 1000 if num_match and "s" in action_text else 1000
            return "wait_for", {"ms": min(ms, 5000)}

        # Default fallback: navigate
        return "navigate", {"url": "/"}

    def execute(self, test_case: TestCase, execution_id: UUID) -> ExecutionOutcome:
        """Execute browser steps in an isolated Playwright Chromium instance."""
        started_at = datetime.now(timezone.utc)
        step_results: list[StepExecutionResult] = []
        overall_status = ExecutionStatus.PASSED
        first_error_message: str | None = None
        error_category: str | None = None
        failed_step_index: int | None = None
        evidence_items = []
        healing_context: dict[str, Any] | None = None

        base_target_url = getattr(test_case, "target_url", None)
        if not base_target_url and hasattr(test_case, "requirement") and test_case.requirement:
            base_target_url = getattr(test_case.requirement, "target_url", None)

        steps = test_case.steps or []
        if not steps:
            steps = [{
                "action": f"Navigate to {test_case.title}",
                "expected_result": test_case.expected_result,
                "data": {"action": "navigate", "url": "/"},
            }]

        timeout_ms = int(self.settings.browser_timeout_seconds * 1000)

        # Event logs collected during test run
        console_logs: list[dict[str, Any]] = []
        page_errors: list[str] = []
        failed_requests: list[str] = []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.settings.browser_headless,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                )
                context = browser.new_context()

                # SSRF Protection Route Interceptor: abort requests to prohibited internal destinations
                def _ssrf_route_interceptor(route):
                    try:
                        p_url = urlparse(route.request.url)
                        h = (p_url.hostname or "").lower()
                        blocked, _ = is_blocked_host(h)
                        if blocked:
                            route.abort("blockedbyclient")
                            return
                        route.continue_()
                    except Exception:
                        route.continue_()

                if hasattr(context, "route") and callable(getattr(context, "route")):
                    try:
                        context.route("**/*", _ssrf_route_interceptor)
                    except Exception:
                        pass

                page = context.new_page()
                page.set_default_timeout(timeout_ms)

                # Attach browser listeners
                def on_console(msg):
                    if msg.type in ("error", "warning"):
                        console_logs.append({
                            "type": msg.type,
                            "text": msg.text,
                            "location": msg.location,
                        })

                def on_pageerror(err):
                    page_errors.append(str(err))

                def on_requestfailed(req):
                    failed_requests.append(f"{req.method} {req.url} - {req.failure}")

                page.on("console", on_console)
                page.on("pageerror", on_pageerror)
                page.on("requestfailed", on_requestfailed)

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
                                target_url = self._validate_target_url(raw_url, base_url=base_target_url)
                                page.goto(target_url, timeout=timeout_ms)
                                actual_result = f"Navigated to {page.url}"

                            elif action_type == "click":
                                locator = self._resolve_locator(page, params)
                                locator.first.click(timeout=timeout_ms)
                                actual_result = f"Clicked element matching {params}"

                            elif action_type in ("fill", "type"):
                                locator = self._resolve_locator(page, params)
                                value = str(params.get("value", ""))
                                locator.first.fill(value, timeout=timeout_ms)
                                actual_result = f"Filled element with value '{value}'"

                            elif action_type == "select":
                                locator = self._resolve_locator(page, params)
                                value = str(params.get("value", ""))
                                locator.first.select_option(value, timeout=timeout_ms)
                                actual_result = f"Selected option '{value}'"

                            elif action_type == "check":
                                locator = self._resolve_locator(page, params)
                                locator.first.check(timeout=timeout_ms)
                                actual_result = "Checked checkbox element"

                            elif action_type == "uncheck":
                                locator = self._resolve_locator(page, params)
                                locator.first.uncheck(timeout=timeout_ms)
                                actual_result = "Unchecked checkbox element"

                            elif action_type == "assert_visible":
                                locator = self._resolve_locator(page, params)
                                is_vis = locator.first.is_visible()
                                if is_vis:
                                    actual_result = f"Element is visible on page ({params})"
                                else:
                                    raise AssertionError(f"Expected element to be visible, but it was not found ({params}).")

                            elif action_type == "assert_title":
                                expected_title = params.get("title") or ""
                                current_title = page.title()
                                if expected_title.lower() in current_title.lower():
                                    actual_result = f"Page title '{current_title}' matches expected '{expected_title}'"
                                else:
                                    raise AssertionError(f"Expected page title to contain '{expected_title}', got '{current_title}'")

                            elif action_type == "assert_url":
                                expected_path = params.get("url") or ""
                                current = page.url
                                if expected_path.lower() in current.lower():
                                    actual_result = f"Current URL '{current}' contains expected '{expected_path}'"
                                else:
                                    raise AssertionError(f"Expected URL to contain '{expected_path}', got '{current}'")

                            elif action_type == "assert_text":
                                expected_content = params.get("text") or params.get("expected") or ""
                                matches = page.get_by_text(expected_content)
                                match_count = matches.count()
                                is_visible = False
                                for i in range(min(match_count, 5)):
                                    try:
                                        if matches.nth(i).is_visible():
                                            is_visible = True
                                            break
                                    except Exception:
                                        pass

                                if is_visible:
                                    actual_result = f"Found visible text '{expected_content}' on page"
                                else:
                                    raise AssertionError(f"Expected text '{expected_content}' not found or not visible on page.")

                            elif action_type == "wait_for":
                                wait_ms = int(params.get("ms", 1000))
                                page.wait_for_timeout(min(wait_ms, 5000))
                                actual_result = f"Waited for {min(wait_ms, 5000)}ms"

                            else:
                                actual_result = f"Skipped unsupported or informational action: {action_type}"

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
                            failed_step_index = idx

                            if not first_error_message:
                                first_error_message = err_msg

                            # Categorize error: distinguish assertion failure from infrastructure errors
                            if isinstance(step_exc, AssertionError):
                                error_category = ErrorCategory.ASSERTION_FAILURE.value
                            elif "security" in err_msg.lower() or "blocked" in err_msg.lower():
                                error_category = ErrorCategory.SECURITY_VIOLATION.value
                            elif "timeout" in err_msg.lower():
                                error_category = ErrorCategory.TIMEOUT.value
                            elif "locator" in err_msg.lower() or "not found" in err_msg.lower():
                                error_category = ErrorCategory.ELEMENT_NOT_FOUND.value
                            else:
                                error_category = ErrorCategory.APPLICATION_ERROR.value

                            # Check if failure is an eligible selector failure for Phase 12 Self-Healing
                            from app.services.self_healing_service import (
                                classify_selector_failure,
                                extract_page_dom_context,
                                generate_candidate_selectors,
                                validate_candidates_live,
                            )
                            is_selector_failure, sel_category = classify_selector_failure(action_type, err_msg)
                            if is_selector_failure:
                                try:
                                    dom_ctx = extract_page_dom_context(page)
                                    candidates = generate_candidate_selectors(
                                        original_selector=params,
                                        action_type=action_type,
                                        action_text=action_text,
                                        dom_elements=dom_ctx.get("elements", []),
                                    )
                                    validation_results = validate_candidates_live(
                                        page=page,
                                        candidates=candidates,
                                        action_type=action_type,
                                        original_selector=params,
                                        action_text=action_text,
                                    )
                                    page_url_val = ""
                                    page_title_val = ""
                                    try:
                                        page_url_val = page.url
                                        page_title_val = page.title()
                                    except Exception:
                                        pass
                                    healing_context = {
                                        "step_index": idx,
                                        "action_type": action_type,
                                        "original_selector": params,
                                        "failure_reason": err_msg,
                                        "failure_category": sel_category or "element_not_found",
                                        "page_url": page_url_val,
                                        "page_title": page_title_val,
                                        "dom_context": dom_ctx,
                                        "candidate_validation_results": validation_results,
                                    }
                                    logger.info(
                                        "Self-healing diagnostic captured for step %d: %d candidates evaluated",
                                        idx,
                                        len(validation_results),
                                    )
                                except Exception as heal_diag_exc:
                                    logger.warning("Could not complete self-healing diagnostic: %s", heal_diag_exc)

                            # Capture screenshot on failure
                            try:
                                screenshot_bytes = page.screenshot(full_page=True)
                                ev = self.evidence_manager.save_screenshot(
                                    execution_id=execution_id,
                                    step_index=idx,
                                    image_bytes=screenshot_bytes,
                                    label=f"Failure screenshot for step {idx}",
                                    metadata={"status": "failed", "error": err_msg, "error_category": error_category},
                                )
                                evidence_items.append(ev)
                            except Exception as ss_exc:
                                logger.warning("Could not capture failure screenshot: %s", ss_exc)

                            step_results.append(
                                StepExecutionResult(
                                    step_index=idx,
                                    action=action_text,
                                    status="failed",
                                    expected=expected_text,
                                    actual=f"Failure: {err_msg}",
                                    duration_ms=round(step_duration, 2),
                                    error_message=err_msg,
                                    details={"error": err_msg, "error_category": error_category},
                                )
                            )
                            break

                    # If passed, capture a completion screenshot
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
                        except Exception as ss_exc:
                            logger.warning("Could not capture pass screenshot: %s", ss_exc)

                finally:
                    context.close()
                    browser.close()

        except Exception as infra_exc:
            overall_status = ExecutionStatus.ERROR
            err_msg = str(infra_exc)
            first_error_message = err_msg
            error_category = ErrorCategory.INFRASTRUCTURE_ERROR.value
            logger.error("Browser runner infrastructure error: %s", infra_exc, exc_info=True)

        # Save collected browser logs as an execution evidence log
        if console_logs or page_errors or failed_requests:
            try:
                log_lines = []
                if page_errors:
                    log_lines.append("=== PAGE ERRORS ===")
                    for pe in page_errors:
                        log_lines.append(f"ERROR: {pe}")
                if console_logs:
                    log_lines.append("=== CONSOLE LOGS ===")
                    for cl in console_logs:
                        log_lines.append(f"[{cl.get('type', 'log').upper()}] {cl.get('text', '')}")
                if failed_requests:
                    log_lines.append("=== FAILED NETWORK REQUESTS ===")
                    for fr in failed_requests:
                        log_lines.append(f"FAILED: {fr}")

                full_log_text = "\n".join(log_lines)
                log_ev = self.evidence_manager.save_log(
                    execution_id=execution_id,
                    log_text=full_log_text,
                    label="Browser Console & Network Logs",
                    metadata={
                        "console_errors_count": len(console_logs),
                        "page_errors_count": len(page_errors),
                        "failed_requests_count": len(failed_requests),
                    },
                )
                evidence_items.append(log_ev)
            except Exception as log_save_exc:
                logger.warning("Could not persist browser log evidence: %s", log_save_exc)

        completed_at = datetime.now(timezone.utc)
        return ExecutionOutcome(
            status=overall_status,
            step_results=step_results,
            error_message=first_error_message,
            error_category=error_category,
            failed_step_index=failed_step_index,
            evidence_items=evidence_items,
            healing_context=healing_context,
            started_at=started_at,
            completed_at=completed_at,
        )
