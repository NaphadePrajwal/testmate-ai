class ResourceNotFoundError(Exception):
    """Raised when a requested resource does not exist in its parent context."""


class ResourceConflictError(Exception):
    """Raised when an operation would violate a domain or database constraint."""
