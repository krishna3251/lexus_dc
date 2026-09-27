"""
Lifecycle and background task management for Lexus bot and security engine.
Ensures bounded task execution, graceful cancellation, and clean resource release.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Coroutine, Any, Optional, Set

logger = logging.getLogger(__name__)


class TaskManager:
    """Tracks and bounds background asyncio tasks to prevent task leaks and dangling loops."""

    def __init__(self, max_concurrent: int = 100):
        self._max_concurrent = max_concurrent
        self._tasks: Set[asyncio.Task] = set()
        self._is_shutting_down: bool = False

    @property
    def active_count(self) -> int:
        return len(self._tasks)

    def spawn(self, coro: Coroutine[Any, Any, Any], name: Optional[str] = None) -> Optional[asyncio.Task]:
        """Spawn a tracked task with bounded concurrency and automatic cleanup."""
        if self._is_shutting_down:
            logger.warning(f"Rejecting task {name or 'unnamed'}: system is shutting down.")
            coro.close()
            return None

        if len(self._tasks) >= self._max_concurrent:
            logger.error(f"Task capacity reached ({self._max_concurrent}). Dropping task {name or 'unnamed'}.")
            coro.close()
            return None

        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)

        def _cleanup(t: asyncio.Task) -> None:
            self._tasks.discard(t)
            if not t.cancelled():
                exc = t.exception()
                if exc:
                    logger.error(f"Background task {t.get_name()} failed with exception: {exc}", exc_info=exc)

        task.add_done_callback(_cleanup)
        return task

    async def shutdown(self, timeout: float = 5.0) -> None:
        """Cancel and wait for all active tasks during shutdown."""
        self._is_shutting_down = True
        if not self._tasks:
            return

        logger.info(f"Cancelling {len(self._tasks)} background tasks...")
        for task in list(self._tasks):
            if not task.done():
                task.cancel()

        try:
            await asyncio.wait(self._tasks, timeout=timeout)
        except Exception as e:
            logger.error(f"Error while waiting for background tasks to shut down: {e}")
        finally:
            self._tasks.clear()
            logger.info("Background tasks shutdown complete.")


# Global default task manager
task_manager = TaskManager(max_concurrent=200)
