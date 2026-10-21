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


def enum_values(enum_class: type[StrEnum]) -> list[str]:
    """Store enum values (not Python member names) in PostgreSQL."""

    return [member.value for member in enum_class]
