class RequirementAnalysisError(Exception):
    """Base exception for safe requirement-analysis failures."""


class AnalysisConfigurationError(RequirementAnalysisError):
    """Raised when analysis cannot run because its provider is not configured."""


class AnalysisInputError(RequirementAnalysisError):
    """Raised when a stored requirement has no usable content to analyze."""


class AnalysisProviderError(RequirementAnalysisError):
    """Raised when the configured provider cannot complete an analysis."""


class InvalidAnalysisOutputError(RequirementAnalysisError):
    """Raised when the provider response is not valid structured analysis."""
