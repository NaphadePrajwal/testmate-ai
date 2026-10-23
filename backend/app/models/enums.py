from enum import StrEnum


class RequirementStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    OBSOLETE = "obsolete"


class TestCaseStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    RETIRED = "retired"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TestType(StrEnum):
    WEB = "web"
    API = "api"
    MANUAL = "manual"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    CANCELLED = "cancelled"


class EvidenceType(StrEnum):
    SCREENSHOT = "screenshot"
    VIDEO = "video"
    LOG = "log"
    TRACE = "trace"
    REQUEST_RESPONSE = "request_response"


class DefectStatus(StrEnum):
    NEW = "new"
    TRIAGED = "triaged"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REVOKED = "revoked"


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED_FOR_APPROVAL = "paused_for_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStage(StrEnum):
    INITIALIZATION = "initialization"
    REQUIREMENT_ANALYSIS = "requirement_analysis"
    TEST_CASE_GENERATION = "test_case_generation"
    HUMAN_APPROVAL = "human_approval"
    TEST_EXECUTION = "test_execution"
    HISTORICAL_RAG = "historical_rag"
    FAILURE_ANALYSIS = "failure_analysis"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowApprovalAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REVISION = "request_revision"


class HealingStatus(StrEnum):
    DETECTED = "detected"
    ANALYZING = "analyzing"
    PROPOSED = "proposed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    VALIDATING = "validating"
    HEALED = "healed"
    FAILED = "failed"


class HealingApprovalAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


def enum_values(enum_class: type[StrEnum]) -> list[str]:
    """Store enum values (not Python member names) in PostgreSQL."""

    return [member.value for member in enum_class]

