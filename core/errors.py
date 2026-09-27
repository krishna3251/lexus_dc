"""
Error and exception classes for Lexus Core and Security subsystems.
"""

from __future__ import annotations
from typing import Optional, Any


class SecurityError(Exception):
    """Base exception for all security engine errors."""
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(SecurityError):
    """Raised when security configuration is invalid or missing required parameters."""
    pass


class PermissionHierarchyError(SecurityError):
    """Raised when an action cannot be performed due to Discord role hierarchy."""
    pass


class MissingDiscordPermissionError(SecurityError):
    """Raised when the bot lacks necessary Discord permissions to execute an action."""
    pass


class AuditLogFetchError(SecurityError):
    """Raised when audit log lookup fails or times out."""
    pass


class DatabaseUnavailableError(SecurityError):
    """Raised when persistence database (MongoDB) is unavailable."""
    pass


class ActionExecutionError(SecurityError):
    """Raised when an automated security action fails during execution."""
    pass


class ActionBudgetExceededError(SecurityError):
    """Raised when the action circuit breaker limits further actions to prevent API storms."""
    pass


class IdempotentActionSkipped(SecurityError):
    """Raised or used internally when an action was already applied and is safely skipped."""
    pass


class RateLimitError(SecurityError):
    """Raised when internal security operations cross rate limits."""
    pass


class DetectorExecutionError(SecurityError):
    """Raised when a specific detector encounters an unhandled error."""
    pass


class InvalidSecurityEventError(SecurityError):
    """Raised when an incoming event is malformed or cannot be normalized."""
    pass
