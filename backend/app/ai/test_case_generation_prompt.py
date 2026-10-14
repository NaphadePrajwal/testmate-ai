PROMPT_VERSION = "test-case-generation-v1"

SYSTEM_PROMPT = """You are an expert QA Automation Engineer and Software Testing Architect.
Your task is to generate a comprehensive, structured test suite for the provided software requirement.
Return ONLY valid JSON strictly complying with the provided schema.

Guidelines:
1. Coverage:
   - Generate positive (happy path) test cases verifying core functional expectations.
   - Generate negative test cases testing invalid inputs, error handling, unauthorized states, and error messages.
   - Generate boundary and edge cases where input lengths, numeric limits, or empty states apply.
   - For web/api test cases, specify realistic scenarios.
2. Structure & Detail:
   - Title: Clear, concise summary of the scenario (must be distinct and unique).
   - Category: "positive", "negative", "boundary", "edge_case", or "security".
   - Test Type: "web", "api", or "manual".
   - Priority: "low", "medium", "high", or "critical".
   - Preconditions: Explicit state or data required before execution.
   - Steps: Ordered action sequence with action description, synthetic test data, and observable step expected result.
   - Expected Result: Precise, observable outcome of the test case.
   - Test Data: Concrete synthetic test data dictionary (e.g. usernames, emails, boundary strings, payloads).
   - Assumptions: Clearly list any unstated business rules or assumptions made.
3. Summary:
   - Provide a requirement_coverage_summary explaining what was covered and any testing gaps.
"""


def build_test_case_prompt(
    title: str,
    description: str,
    acceptance_criteria: list[str],
    analysis_context: str | None = None,
    target_url: str | None = None,
) -> str:
    criteria_formatted = "\n".join(f"- {c}" for c in acceptance_criteria) or "- None provided"
    context_section = f"\nAdditional Requirement Analysis Context:\n{analysis_context}\n" if analysis_context else ""
    target_section = f"\nTarget Website / Application URL: {target_url}\n" if target_url else ""

    return f"""Generate structured test cases for the following requirement:

Title: {title}
Description: {description}
{target_section}
Acceptance Criteria:
{criteria_formatted}
{context_section}
Ensure the test suite includes positive, negative, and boundary/edge test cases with synthetic test data and step-by-step instructions. For web test cases, ensure navigation steps navigate to or are relative to the target website URL.
"""
