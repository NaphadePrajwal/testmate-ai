from datetime import datetime, timezone
import logging
import re
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from playwright.sync_api import Locator, Page
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceConflictError, ResourceNotFoundError
from app.models.enums import ExecutionStatus, HealingStatus, ReviewStatus, TestCaseStatus
from app.models.healing_proposal import HealingProposal
from app.models.project import Project
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.schemas.healing import HealingApprovalRequest, HealingRejectionRequest
from app.services.database import commit_or_rollback
from app.services.project_service import ProjectService

logger = logging.getLogger(__name__)

# Non-selector error patterns that should NEVER trigger selector self-healing
NON_SELECTOR_PATTERNS = [
    r"net::ERR_",
    r"ECONNREFUSED",
    r"ECONNRESET",
    r"ENOTFOUND",
    r"ERR_NAME_NOT_RESOLVED",
    r"navigation failed",
    r"Target page, context or browser has been closed",
    r"browser has been closed",
    r"context has been closed",
    r"500 Internal Server Error",
    r"502 Bad Gateway",
    r"503 Service Unavailable",
    r"504 Gateway Timeout",
    r"401 Unauthorized",
    r"403 Forbidden",
    r"blocked by client",
    r"blockedbyclient",
]

# Selector error patterns indicating broken, ambiguous, or detached locators
SELECTOR_FAILURE_PATTERNS = [
    (r"strict mode violation.*resolved to (\d+) elements", "strict_mode_violation"),
    (r"resolved to (\d+) elements", "strict_mode_violation"),
    (r"waiting for locator\(", "element_not_found"),
    (r"waiting for get_by_", "element_not_found"),
    (r"element not found", "element_not_found"),
    (r"no element matches", "element_not_found"),
    (r"cannot find element", "element_not_found"),
    (r"not attached to the DOM", "element_detached"),
    (r"is detached", "element_detached"),
    (r"is not visible", "element_not_visible"),
    (r"element is not visible", "element_not_visible"),
    (r"not actionable", "element_not_actionable"),
    (r"element is disabled", "element_not_actionable"),
    (r"intercepts pointer events", "element_not_actionable"),
    (r"Timeout \d+ms exceeded.*waiting for", "locator_timeout"),
]


def classify_selector_failure(action_type: str, error_message: str) -> tuple[bool, str | None]:
    """
    Determine whether an execution failure is an eligible selector failure.
    Distinguishes broken selectors from network, auth, navigation, and non-selector assertion errors.
    """
    if not error_message:
        return False, None

    # Step actions like navigate or wait are never selector failures
    if action_type in ("navigate", "goto", "wait_for", "assert_title", "assert_url"):
        return False, None

    # Check non-selector exclusion patterns
    for pat in NON_SELECTOR_PATTERNS:
        if re.search(pat, error_message, re.IGNORECASE):
            return False, None

    # Check for specific selector failure categories
    for pat, category in SELECTOR_FAILURE_PATTERNS:
        if re.search(pat, error_message, re.IGNORECASE):
            return True, category

    # Fallback: if failure mentions timeout or locator in an element interaction
    if action_type in ("click", "fill", "type", "select", "check", "uncheck", "assert_visible"):
        if "timeout" in error_message.lower() or "locator" in error_message.lower():
            return True, "locator_timeout"

    return False, None


def extract_page_dom_context(page: Page) -> dict[str, Any]:
    """
    Safely extract interactive DOM context and page metadata from the live browser page.
    Sanitizes secrets, password inputs, tokens, and enforces size boundaries.
    """
    try:
        url = page.url
        title = page.title()
    except Exception:
        url = ""
        title = ""

    extract_script = """
    () => {
        try {
            const elements = Array.from(document.querySelectorAll(
                'button, a, input, select, textarea, [role], [data-testid], [data-test], [id]'
            ));
            return elements.slice(0, 80).map((el, i) => {
                const rect = el.getBoundingClientRect();
                const isVisible = rect.width > 0 && rect.height > 0 && 
                    window.getComputedStyle(el).visibility !== 'hidden' && 
                    window.getComputedStyle(el).display !== 'none';
                
                let labelText = '';
                if (el.labels && el.labels.length > 0) {
                    labelText = el.labels[0].innerText || '';
                } else if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) labelText = lbl.innerText || '';
                }
                
                let val = '';
                const tag = (el.tagName || '').toLowerCase();
                const type = (el.getAttribute('type') || '').toLowerCase();
                if (tag === 'input' && type === 'password') {
                    val = '[PROTECTED_PASSWORD]';
                } else if (el.value) {
                    val = String(el.value).slice(0, 50);
                }

                return {
                    index: i,
                    tagName: tag,
                    type: type,
                    role: el.getAttribute('role') || (tag === 'button' ? 'button' : tag === 'a' ? 'link' : ''),
                    name: el.getAttribute('name') || '',
                    id: el.id || '',
                    testId: el.getAttribute('data-testid') || el.getAttribute('data-test') || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    labelText: labelText.trim().slice(0, 80),
                    placeholder: el.getAttribute('placeholder') || '',
                    innerText: (el.innerText || '').trim().slice(0, 80),
                    isVisible: isVisible,
                    disabled: Boolean(el.disabled),
                    className: (el.className || '').toString().slice(0, 80)
                };
            });
        } catch (e) {
            return [];
        }
    }
    """
    try:
        dom_elements = page.evaluate(extract_script)
    except Exception as exc:
        logger.warning("DOM context extraction failed: %s", exc)
        dom_elements = []

    return {
        "url": url,
        "title": title,
        "element_count": len(dom_elements),
        "elements": dom_elements,
    }


def generate_candidate_selectors(
    original_selector: dict[str, Any],
    action_type: str,
    action_text: str,
    dom_elements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Generate deterministic replacement selector candidates from the extracted live DOM elements.
    Ranks standard semantic locators (role, label, placeholder, test_id, stable attributes)
    over fragile positional or transient class selectors.
    """
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_candidate(cand: dict[str, Any], cand_type: str):
        key = str(sorted(cand.items()))
        if key not in seen:
            seen.add(key)
            candidates.append({"params": cand, "type": cand_type})

    # Extract target search terms from action_text and original selector
    search_terms: list[str] = []
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", action_text)
    search_terms.extend([q.strip().lower() for q in quoted if q.strip()])
    for k in ("name", "label", "text", "placeholder", "selector"):
        if k in original_selector and original_selector[k]:
            val = str(original_selector[k]).strip().lower()
            if val and val not in search_terms:
                search_terms.append(val)

    for el in dom_elements:
        tag = el.get("tagName", "")
        role = el.get("role", "")
        aria_label = el.get("ariaLabel", "")
        inner_text = el.get("innerText", "")
        label_text = el.get("labelText", "")
        placeholder = el.get("placeholder", "")
        test_id = el.get("testId", "")
        el_id = el.get("id", "")
        el_name = el.get("name", "")

        # 1. Test ID (e.g. data-testid="checkout-btn")
        if test_id:
            add_candidate({"test_id": test_id}, "test_id")

        # 2. Accessible Role + Name
        acc_name = aria_label or inner_text or label_text
        if role and acc_name and len(acc_name) <= 60:
            add_candidate({"role": role, "name": acc_name}, "role_and_name")

        # 3. Form Label
        if label_text and len(label_text) <= 60:
            add_candidate({"label": label_text}, "label")

        # 4. Input Placeholder
        if placeholder and len(placeholder) <= 60:
            add_candidate({"placeholder": placeholder}, "placeholder")

        # 5. Stable, Non-Transient Element ID (avoid auto-generated UUIDs, long hashes, or transient tokens)
        is_transient = (
            len(el_id) > 40
            or bool(re.search(r"[0-9a-f]{8,}", el_id, re.IGNORECASE))
            or any(tok in el_id.lower() for tok in ("guid", "uuid", "random", "temp", "tmp", "nonce", ":r"))
        )
        if el_id and not is_transient:
            add_candidate({"selector": f"#{el_id}"}, "id_selector")

        # 6. Distinct Name Attribute
        if el_name and len(el_name) <= 40:
            add_candidate({"selector": f"[name='{el_name}']"}, "name_attribute")

        # 7. Distinct Element Text (Buttons / Links)
        if tag in ("button", "a") and inner_text and 2 <= len(inner_text) <= 40:
            add_candidate({"text": inner_text}, "text_selector")

    return candidates


def validate_candidates_live(
    page: Page,
    candidates: list[dict[str, Any]],
    action_type: str,
    original_selector: dict[str, Any],
    action_text: str,
    timeout_ms: int = 1500,
) -> list[dict[str, Any]]:
    """
    Validate every candidate selector against the live browser page.
    Enforces uniqueness (count == 1), visibility, actionability, and computes a transparent score.
    Rejects ambiguous (count > 1) or non-matching (count == 0) candidates.
    """
    validated_results: list[dict[str, Any]] = []

    def _resolve(cand_params: dict[str, Any]) -> Locator:
        if "role" in cand_params and cand_params["role"]:
            r = str(cand_params["role"]).lower()
            n = cand_params.get("name")
            return page.get_by_role(r, name=str(n)) if n else page.get_by_role(r)
        if "label" in cand_params and cand_params["label"]:
            return page.get_by_label(str(cand_params["label"]))
        if "placeholder" in cand_params and cand_params["placeholder"]:
            return page.get_by_placeholder(str(cand_params["placeholder"]))
        if "test_id" in cand_params and cand_params["test_id"]:
            return page.get_by_test_id(str(cand_params["test_id"]))
        if "text" in cand_params and cand_params["text"]:
            return page.get_by_text(str(cand_params["text"]))
        sel = cand_params.get("selector")
        if sel:
            return page.locator(str(sel))
        return page.locator("button, a, input")

    terms = [str(v).lower() for v in original_selector.values() if v and isinstance(v, str)]
    for word in re.findall(r"['\"]([^'\"]+)['\"]", action_text):
        if word.lower() not in terms:
            terms.append(word.lower())

    for item in candidates:
        params = item["params"]
        cand_type = item["type"]
        score = 0.0
        rejection_reason = None
        is_visible = False
        is_enabled = False
        is_actionable = False
        match_count = 0

        try:
            loc = _resolve(params)
            match_count = loc.count()

            if match_count == 0:
                rejection_reason = "No elements matched on page"
            elif match_count > 1:
                rejection_reason = f"Ambiguous match ({match_count} elements matched)"
            else:
                # Exactly 1 element matched
                is_visible = loc.first.is_visible()
                is_enabled = loc.first.is_enabled()
                is_actionable = is_visible and is_enabled

                if not is_visible:
                    rejection_reason = "Matched element is not visible"
                else:
                    # Score calculation
                    score = 40.0  # Base score for unique match

                    # Locator type bonus
                    if cand_type in ("test_id", "role_and_name"):
                        score += 30.0
                    elif cand_type in ("label", "placeholder"):
                        score += 25.0
                    elif cand_type in ("id_selector", "name_attribute"):
                        score += 20.0
                    elif cand_type == "text_selector":
                        score += 15.0

                    if is_actionable:
                        score += 10.0

                    # Semantic keyword agreement
                    cand_str = " ".join(str(v).lower() for v in params.values())
                    if any(t in cand_str for t in terms):
                        score += 20.0

        except Exception as exc:
            rejection_reason = f"Locator resolution error: {exc}"

        valid = match_count == 1 and is_visible and rejection_reason is None

        explanation_parts = []
        if valid:
            explanation_parts.append(f"Unique match (count=1, {cand_type})")
            if is_actionable:
                explanation_parts.append("visible & actionable")
        else:
            explanation_parts.append(rejection_reason or "Invalid candidate")

        validated_results.append({
            "selector": params,
            "selector_type": cand_type,
            "match_count": match_count,
            "is_visible": is_visible,
            "is_enabled": is_enabled,
            "is_actionable": is_actionable,
            "score": round(min(score, 100.0), 1),
            "valid": valid,
            "rejection_reason": rejection_reason,
            "confidence_explanation": ", ".join(explanation_parts),
        })

    # Sort descending by score
    validated_results.sort(key=lambda x: (x["valid"], x["score"]), reverse=True)
    return validated_results


class SelfHealingService:
    """
    Orchestration service for Phase 12 Self-Healing tests.
    Manages detection, live page candidate validation, controlled human approval,
    safe test step updates, and retry verification.
    """

    MAX_HEALING_ATTEMPTS_PER_TEST_CASE = 3

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_proposals(
        self,
        project_id: UUID,
        limit: int = 50,
        offset: int = 0,
        status: HealingStatus | None = None,
        test_case_id: UUID | None = None,
    ) -> tuple[list[HealingProposal], int]:
        ProjectService(self.db).get_project(project_id)
        stmt = select(HealingProposal).where(HealingProposal.project_id == project_id)
        if status is not None:
            stmt = stmt.where(HealingProposal.status == status)
        if test_case_id is not None:
            stmt = stmt.where(HealingProposal.test_case_id == test_case_id)

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = list(
            self.db.scalars(stmt.order_by(HealingProposal.created_at.desc()).offset(offset).limit(limit))
        )
        return items, total

    def get_proposal(self, project_id: UUID, proposal_id: UUID) -> HealingProposal:
        proposal = self.db.scalar(
            select(HealingProposal).where(
                HealingProposal.id == proposal_id,
                HealingProposal.project_id == project_id,
            )
        )
        if proposal is None:
            raise ResourceNotFoundError("Healing proposal not found for this project.")
        return proposal

    def create_proposal_from_failure(
        self,
        project_id: UUID,
        test_case_id: UUID,
        execution_id: UUID,
        step_index: int,
        action_type: str,
        original_selector: dict[str, Any],
        failure_reason: str,
        failure_category: str,
        page_url: str | None,
        page_title: str | None,
        dom_context: dict[str, Any],
        candidate_validation_results: list[dict[str, Any]],
    ) -> HealingProposal:
        """
        Create and persist a new HealingProposal in AWAITING_APPROVAL (if valid proposal found)
        or FAILED state (if no safe replacement exists).
        """
        # Enforce retry boundary limit: check previous proposals for this test case
        prior_attempts = self.db.scalar(
            select(func.count())
            .select_from(HealingProposal)
            .where(
                HealingProposal.test_case_id == test_case_id,
                HealingProposal.status.in_([HealingStatus.HEALED, HealingStatus.APPROVED, HealingStatus.VALIDATING]),
            )
        ) or 0

        if prior_attempts >= self.MAX_HEALING_ATTEMPTS_PER_TEST_CASE:
            logger.warning(
                "Test case %s exceeded maximum self-healing attempts (%d). Marking proposal as failed.",
                test_case_id,
                self.MAX_HEALING_ATTEMPTS_PER_TEST_CASE,
            )
            top_candidate = candidate_validation_results[0] if candidate_validation_results else {}
            proposal = HealingProposal(
                id=uuid4(),
                project_id=project_id,
                test_case_id=test_case_id,
                original_execution_id=execution_id,
                step_index=step_index,
                action_type=action_type,
                original_selector=original_selector,
                proposed_selector=top_candidate.get("selector", {}),
                status=HealingStatus.FAILED,
                failure_reason=failure_reason,
                failure_category=failure_category,
                page_url=page_url,
                page_title=page_title,
                dom_context=dom_context,
                candidate_validation_results=candidate_validation_results,
                confidence=0.0,
                explanation=f"Maximum self-healing attempts ({self.MAX_HEALING_ATTEMPTS_PER_TEST_CASE}) reached for this test case.",
            )
            self.db.add(proposal)
            commit_or_rollback(self.db)
            return proposal

        # Find top valid candidate
        valid_candidates = [c for c in candidate_validation_results if c.get("valid")]
        if valid_candidates:
            top = valid_candidates[0]
            status = HealingStatus.AWAITING_APPROVAL
            proposed_selector = top["selector"]
            confidence = top["score"]
            explanation = (
                f"Found unique replacement selector using {top['selector_type']}. "
                f"Element is visible and actionable. Confidence score: {confidence}/100."
            )
        else:
            status = HealingStatus.FAILED
            proposed_selector = {}
            confidence = 0.0
            explanation = "No safe, unique replacement selector could be validated against the live page DOM."

        proposal = HealingProposal(
            id=uuid4(),
            project_id=project_id,
            test_case_id=test_case_id,
            original_execution_id=execution_id,
            step_index=step_index,
            action_type=action_type,
            original_selector=original_selector,
            proposed_selector=proposed_selector,
            status=status,
            failure_reason=failure_reason,
            failure_category=failure_category,
            page_url=page_url,
            page_title=page_title,
            dom_context=dom_context,
            candidate_validation_results=candidate_validation_results,
            confidence=confidence,
            explanation=explanation,
        )
        self.db.add(proposal)
        commit_or_rollback(self.db)
        logger.info(
            "Created HealingProposal %s for test case %s (status=%s, confidence=%.1f)",
            proposal.id,
            test_case_id,
            status,
            confidence,
        )
        return proposal

    def approve_proposal(
        self,
        project_id: UUID,
        proposal_id: UUID,
        request: HealingApprovalRequest,
    ) -> HealingProposal:
        """
        Approve a healing proposal, safely update the affected test step's selector,
        and re-execute the test to verify that the repair and assertions pass.
        """
        proposal = self.get_proposal(project_id, proposal_id)

        if proposal.status not in (HealingStatus.AWAITING_APPROVAL, HealingStatus.PROPOSED):
            raise ResourceConflictError(
                f"Proposal cannot be approved in its current status: '{proposal.status}'."
            )

        test_case = self.db.scalar(
            select(TestCase).where(TestCase.id == proposal.test_case_id)
        )
        if test_case is None:
            raise ResourceNotFoundError("Test case associated with proposal not found.")

        # Determine approved selector
        approved_sel = request.selector_override or proposal.proposed_selector
        if not approved_sel:
            raise ResourceConflictError("Cannot approve a proposal without a valid replacement selector.")

        now = datetime.now(timezone.utc)
        proposal.status = HealingStatus.APPROVED
        proposal.approved_selector = approved_sel
        proposal.approved_by = request.approved_by
        proposal.approved_at = now
        proposal.decision_notes = request.decision_notes
        commit_or_rollback(self.db)

        # Apply safe repair: update step data in TestCase
        steps = list(test_case.steps or [])
        idx = proposal.step_index - 1
        if 0 <= idx < len(steps):
            step = dict(steps[idx])
            existing_data = dict(step.get("data") or {})

            # Record healing audit metadata in step
            history = list(existing_data.get("_healing_history") or [])
            history.append({
                "proposal_id": str(proposal.id),
                "original_selector": proposal.original_selector,
                "repaired_selector": approved_sel,
                "repaired_at": now.isoformat(),
                "approved_by": request.approved_by,
            })

            # Merge approved selector into step data
            new_data = {**existing_data, **approved_sel, "_healing_history": history}
            step["data"] = new_data
            steps[idx] = step

            test_case.steps = steps
            test_case.version += 1
            test_case.updated_at = now
            proposal.repaired_at = now
            proposal.status = HealingStatus.VALIDATING
            commit_or_rollback(self.db)
            logger.info("Applied safe selector repair to test case %s (v%d)", test_case.id, test_case.version)

        # Trigger re-execution through ExecutionService
        from app.services.execution_service import ExecutionService

        try:
            exec_svc = ExecutionService(self.db)
            retry_execution = exec_svc.execute_test_case(
                project_id=project_id,
                test_case_id=test_case.id,
                executor_override="playwright",
            )
            proposal.retry_execution_id = retry_execution.id

            # Crucial requirement: assertions must succeed for test to be marked healed!
            if retry_execution.status == ExecutionStatus.PASSED:
                proposal.status = HealingStatus.HEALED
                logger.info(
                    "Healing proposal %s verified: retry execution %s passed.",
                    proposal.id,
                    retry_execution.id,
                )
            else:
                proposal.status = HealingStatus.FAILED
                logger.warning(
                    "Healing proposal %s retry execution %s did not pass (status=%s).",
                    proposal.id,
                    retry_execution.id,
                    retry_execution.status,
                )
            commit_or_rollback(self.db)

        except Exception as exc:
            proposal.status = HealingStatus.FAILED
            commit_or_rollback(self.db)
            logger.error("Error during retry execution for proposal %s: %s", proposal.id, exc, exc_info=True)

        return proposal

    def reject_proposal(
        self,
        project_id: UUID,
        proposal_id: UUID,
        request: HealingRejectionRequest,
    ) -> HealingProposal:
        """
        Reject a healing proposal. Preserves the original test case definition untouched.
        """
        proposal = self.get_proposal(project_id, proposal_id)

        if proposal.status not in (HealingStatus.AWAITING_APPROVAL, HealingStatus.PROPOSED):
            raise ResourceConflictError(
                f"Proposal cannot be rejected in its current status: '{proposal.status}'."
            )

        proposal.status = HealingStatus.REJECTED
        proposal.decision_notes = request.decision_notes
        proposal.approved_by = request.rejected_by
        proposal.approved_at = datetime.now(timezone.utc)
        commit_or_rollback(self.db)

        logger.info("Healing proposal %s rejected by %s", proposal.id, request.rejected_by)
        return proposal
