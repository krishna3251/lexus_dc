"""
Structured logging module for Lexus bot and security engine.
Provides clear, audit-ready log streams without leaking secrets.
"""

from __future__ import annotations
import logging
import os
import sys
from typing import Optional, Any
from core.config import config


def setup_logging(
    level: Optional[str] = None,
    log_dir: Optional[str] = None,
    log_file: str = "bot_log.txt",
    security_file: str = "security.log"
) -> logging.Logger:
    """Initialize standardized bot and security loggers."""
    log_level_name = level or config.security_log_level
    numeric_level = getattr(logging, log_level_name.upper(), logging.INFO)
    target_dir = log_dir or config.security_log_dir

    os.makedirs(target_dir, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Avoid duplicate handlers on re-init
    if not root_logger.handlers:
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s]: %(message)s")

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(numeric_level)
        root_logger.addHandler(stream_handler)

        bot_file_path = os.path.join(target_dir, log_file)
        file_handler = logging.FileHandler(bot_file_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(numeric_level)
        root_logger.addHandler(file_handler)

    # Dedicated security logger
    sec_logger = logging.getLogger("security")
    sec_logger.setLevel(numeric_level)

    # Dedicated security file handler
    sec_file_path = os.path.join(target_dir, security_file)
    if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "").endswith(security_file) for h in sec_logger.handlers):
        sec_formatter = logging.Formatter("%(asctime)s [SECURITY] [%(levelname)s]: %(message)s")
        sec_handler = logging.FileHandler(sec_file_path, encoding="utf-8")
        sec_handler.setFormatter(sec_formatter)
        sec_handler.setLevel(numeric_level)
        sec_logger.addHandler(sec_handler)

    return sec_logger


class SecurityLogger:
    """Helper for emitting standardized, structured security log entries."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self._logger = logger or logging.getLogger("security")

    def event(
        self,
        incident_id: str,
        guild_id: int,
        actor_id: Optional[int],
        event_type: str,
        risk: str,
        score: float,
        action: str,
        result: str,
        details: Optional[str] = None
    ) -> None:
        msg = (
            f"SECURITY_EVENT: Incident={incident_id} | Guild={guild_id} | Actor={actor_id} | "
            f"Event={event_type} | Risk={risk} | Score={score:.1f} | Action={action} | Result={result}"
        )
        if details:
            msg += f" | Details={details}"
        self._logger.info(msg)

    def action_failure(
        self,
        guild_id: int,
        action: str,
        target: Any,
        reason: str,
        error: Optional[Exception] = None
    ) -> None:
        err_msg = f" | Error={type(error).__name__}: {error}" if error else ""
        self._logger.error(
            f"ACTION_FAILURE: Guild={guild_id} | Action={action} | Target={target} | Reason={reason}{err_msg}"
        )

    def permission_failure(
        self,
        guild_id: int,
        action: str,
        target: Any,
        reason: str
    ) -> None:
        self._logger.warning(
            f"PERMISSION_FAILURE: Guild={guild_id} | Action={action} | Target={target} | Reason={reason}"
        )

    def hierarchy_failure(
        self,
        guild_id: int,
        action: str,
        target: Any,
        reason: str
    ) -> None:
        self._logger.warning(
            f"HIERARCHY_FAILURE: Guild={guild_id} | Action={action} | Target={target} | Reason={reason}"
        )

    def database_failure(self, operation: str, error: Exception) -> None:
        self._logger.error(
            f"DATABASE_FAILURE: Operation={operation} | Error={type(error).__name__}: {error}"
        )

    def audit_failure(self, guild_id: int, action_type: str, reason: str) -> None:
        self._logger.warning(
            f"AUDIT_LOOKUP_FAILURE: Guild={guild_id} | ActionType={action_type} | Reason={reason}"
        )

    def state_transition(
        self,
        guild_id: int,
        from_state: str,
        to_state: str,
        trigger: str,
        heat: float
    ) -> None:
        self._logger.info(
            f"STATE_TRANSITION: Guild={guild_id} | Transition={from_state}->{to_state} | Trigger={trigger} | Heat={heat:.1f}"
        )


security_logger = SecurityLogger()
