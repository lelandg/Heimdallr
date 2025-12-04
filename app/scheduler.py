"""Task scheduler for periodic monitoring operations.

Provides:
- Periodic health checks
- Log polling at intervals
- Cleanup and maintenance tasks
- Cron-like scheduling
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

log = logging.getLogger("monitor.scheduler")


class TaskStatus(Enum):
    """Status of a scheduled task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledTask:
    """A scheduled task definition."""
    name: str
    func: Callable[[], Coroutine[Any, Any, Any]]
    interval_s: int
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    last_status: TaskStatus = TaskStatus.PENDING
    last_error: Optional[str] = None
    run_count: int = 0
    error_count: int = 0

    def __post_init__(self):
        if self.next_run is None:
            self.next_run = datetime.now(timezone.utc)


@dataclass
class TaskResult:
    """Result of a task execution."""
    task_name: str
    status: TaskStatus
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    error: Optional[str] = None


class Scheduler:
    """Task scheduler for periodic operations.

    Features:
    - Interval-based scheduling
    - Concurrent task execution
    - Error handling and retry
    - Task enable/disable
    - Execution history
    """

    def __init__(self):
        """Initialize the scheduler."""
        self._tasks: Dict[str, ScheduledTask] = {}
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._execution_history: List[TaskResult] = []
        self._max_history = 500

    def add_task(
        self,
        name: str,
        func: Callable[[], Coroutine[Any, Any, Any]],
        interval_s: int,
        enabled: bool = True,
        run_immediately: bool = False,
    ) -> None:
        """Add a scheduled task.

        Args:
            name: Unique task name
            func: Async function to execute
            interval_s: Interval between runs in seconds
            enabled: Whether task is enabled
            run_immediately: Run once immediately on start
        """
        next_run = datetime.now(timezone.utc)
        if not run_immediately:
            next_run += timedelta(seconds=interval_s)

        self._tasks[name] = ScheduledTask(
            name=name,
            func=func,
            interval_s=interval_s,
            enabled=enabled,
            next_run=next_run,
        )
        log.info(f"Task added: {name} (every {interval_s}s)")

    def remove_task(self, name: str) -> bool:
        """Remove a scheduled task.

        Args:
            name: Task name to remove

        Returns:
            True if task was removed
        """
        if name in self._tasks:
            del self._tasks[name]
            log.info(f"Task removed: {name}")
            return True
        return False

    def enable_task(self, name: str) -> bool:
        """Enable a task."""
        if name in self._tasks:
            self._tasks[name].enabled = True
            log.info(f"Task enabled: {name}")
            return True
        return False

    def disable_task(self, name: str) -> bool:
        """Disable a task."""
        if name in self._tasks:
            self._tasks[name].enabled = False
            log.info(f"Task disabled: {name}")
            return True
        return False

    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            log.warning("Scheduler already running")
            return

        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        log.info(f"Scheduler started with {len(self._tasks)} tasks")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        log.info("Scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self._check_and_run_tasks()
            except Exception as e:
                log.error(f"Scheduler error: {e}")

            # Sleep briefly before next check
            await asyncio.sleep(1)

    async def _check_and_run_tasks(self) -> None:
        """Check for due tasks and run them."""
        now = datetime.now(timezone.utc)

        for task in self._tasks.values():
            if not task.enabled:
                continue

            if task.last_status == TaskStatus.RUNNING:
                continue  # Already running

            if task.next_run and task.next_run <= now:
                # Task is due
                asyncio.create_task(self._run_task(task))

    async def _run_task(self, task: ScheduledTask) -> None:
        """Execute a task and update its state."""
        task.last_status = TaskStatus.RUNNING
        started_at = datetime.now(timezone.utc)

        log.debug(f"Running task: {task.name}")

        try:
            await task.func()

            task.last_status = TaskStatus.COMPLETED
            task.last_error = None
            log.debug(f"Task completed: {task.name}")

        except Exception as e:
            task.last_status = TaskStatus.FAILED
            task.last_error = str(e)
            task.error_count += 1
            log.error(f"Task failed: {task.name} - {e}")

        completed_at = datetime.now(timezone.utc)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        # Update task state
        task.last_run = started_at
        task.next_run = datetime.now(timezone.utc) + timedelta(seconds=task.interval_s)
        task.run_count += 1

        # Record in history
        result = TaskResult(
            task_name=task.name,
            status=task.last_status,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            error=task.last_error,
        )
        self._execution_history.append(result)
        if len(self._execution_history) > self._max_history:
            self._execution_history.pop(0)

    async def run_now(self, name: str) -> Optional[TaskResult]:
        """Run a task immediately.

        Args:
            name: Task name to run

        Returns:
            TaskResult or None if task not found
        """
        if name not in self._tasks:
            return None

        task = self._tasks[name]
        await self._run_task(task)

        return self._execution_history[-1] if self._execution_history else None

    def get_task(self, name: str) -> Optional[ScheduledTask]:
        """Get task by name."""
        return self._tasks.get(name)

    def get_all_tasks(self) -> List[ScheduledTask]:
        """Get all tasks."""
        return list(self._tasks.values())

    def get_history(self, task_name: Optional[str] = None, limit: int = 50) -> List[TaskResult]:
        """Get execution history.

        Args:
            task_name: Filter by task name
            limit: Maximum results

        Returns:
            List of TaskResults
        """
        history = self._execution_history
        if task_name:
            history = [r for r in history if r.task_name == task_name]
        return list(reversed(history[-limit:]))

    def get_stats(self) -> Dict:
        """Get scheduler statistics."""
        total_runs = sum(t.run_count for t in self._tasks.values())
        total_errors = sum(t.error_count for t in self._tasks.values())

        return {
            "running": self._running,
            "total_tasks": len(self._tasks),
            "enabled_tasks": sum(1 for t in self._tasks.values() if t.enabled),
            "total_runs": total_runs,
            "total_errors": total_errors,
            "history_size": len(self._execution_history),
        }


def create_monitor_scheduler(monitor_app) -> Scheduler:
    """Create a scheduler with standard monitoring tasks.

    Args:
        monitor_app: MonitorApp instance

    Returns:
        Configured Scheduler
    """
    scheduler = Scheduler()

    # Health check task
    async def health_check_task():
        await monitor_app.service_monitor.force_check()

    scheduler.add_task(
        name="health_check",
        func=health_check_task,
        interval_s=monitor_app.config.monitoring.health_check_interval,
        run_immediately=True,
    )

    # Alert cleanup task
    async def alert_cleanup_task():
        count = monitor_app.alert_manager.clear_old_alerts(hours=24)
        if count:
            log.info(f"Cleaned up {count} old alerts")

    scheduler.add_task(
        name="alert_cleanup",
        func=alert_cleanup_task,
        interval_s=3600,  # Hourly
    )

    # LLM health check task
    async def llm_health_task():
        await monitor_app.llm_client.test_connection()

    scheduler.add_task(
        name="llm_health_check",
        func=llm_health_task,
        interval_s=300,  # Every 5 minutes
    )

    # Audit log rotation check
    async def audit_rotation_task():
        # Placeholder for log rotation logic
        pass

    scheduler.add_task(
        name="audit_rotation",
        func=audit_rotation_task,
        interval_s=86400,  # Daily
        enabled=False,  # Disabled by default
    )

    return scheduler
