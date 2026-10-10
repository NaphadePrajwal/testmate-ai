PROMPT_VERSION = "requirement-analysis-v1"

SYSTEM_PROMPT = """You analyze one software requirement. Return only JSON matching the supplied schema.
Ground every conclusion in the source requirement. Mark direct statements as explicit; use inferred only
for cautious interpretations; use suggested only for proposed acceptance criteria or clarification questions;
and use unspecified when required information is absent. Never invent business behavior. For each of
preconditions, postconditions, and acceptance_criteria, include an unspecified item when none is stated.
Quality labels assess only clarity and completeness of the supplied text, not correctness. Explain their limits."""


def build_requirement_prompt(title: str, description: str, acceptance_criteria: list[str]) -> str:
    criteria = "\n".join(f"- {item}" for item in acceptance_criteria) or "- None supplied"
    return f"""Analyze this stored requirement.

Title: {title}
Description: {description}
Existing acceptance criteria:
{criteria}
"""
