"""TestMate AI Test Execution Engine (Phase 5).

Provides deterministic and isolated test execution adapters:
- PlaywrightWebRunner for browser-based UI automation
- HttpxApiRunner for HTTP REST API testing
- PytestRunner for deterministic Python unit/integration template tests
- EvidenceManager for local durable evidence and artifact management
"""

from app.testing.contract import EvidencePayload, ExecutionOutcome, StepExecutionResult
from app.testing.evidence_manager import EvidenceManager
from app.testing.httpx_runner import HttpxApiRunner
from app.testing.playwright_runner import PlaywrightWebRunner
from app.testing.pytest_runner import PytestRunner

__all__ = [
    "EvidenceManager",
    "EvidencePayload",
    "ExecutionOutcome",
    "HttpxApiRunner",
    "PlaywrightWebRunner",
    "PytestRunner",
    "StepExecutionResult",
]
