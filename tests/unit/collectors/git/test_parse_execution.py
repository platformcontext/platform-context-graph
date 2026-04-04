"""Tests for Git parse task cleanup and failure containment helpers."""

from __future__ import annotations

import asyncio
from typing import Any

from platform_context_graph.collectors.git.parse_execution import (
    _cancel_and_drain_parse_tasks,
)


class _FakeTask:
    """Minimal task stub for cancellation and drain tests."""

    def __init__(self, *, done: bool) -> None:
        self._done = done
        self.cancel_called = False

    def done(self) -> bool:
        """Return whether the task is already done."""

        return self._done

    def cancel(self) -> None:
        """Record task cancellation."""

        self.cancel_called = True


class _FakeAsyncioModule:
    """Minimal asyncio-like module used to observe gather arguments."""

    def __init__(self) -> None:
        self.gather_calls: list[tuple[tuple[Any, ...], bool]] = []

    async def gather(self, *tasks: Any, return_exceptions: bool = False) -> list[Any]:
        """Capture drain requests and emulate successful gathering."""

        self.gather_calls.append((tasks, return_exceptions))
        return [None for _task in tasks]


def test_cancel_and_drain_parse_tasks_cancels_pending_and_gathers_all() -> None:
    """Pending parse tasks should be cancelled and all tasks should be drained."""

    done_task = _FakeTask(done=True)
    pending_task = _FakeTask(done=False)
    asyncio_module = _FakeAsyncioModule()

    asyncio.run(
        _cancel_and_drain_parse_tasks(
            [done_task, pending_task],
            asyncio_module=asyncio_module,
        )
    )

    assert done_task.cancel_called is False
    assert pending_task.cancel_called is True
    assert asyncio_module.gather_calls == [
        ((done_task, pending_task), True),
    ]
