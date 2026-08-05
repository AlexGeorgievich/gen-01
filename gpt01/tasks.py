from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from .errors import OperationCancelled

LOGGER = logging.getLogger(__name__)
TaskFunction = Callable[[Callable[[], bool]], Any]


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, function: TaskFunction) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function(self._cancelled.is_set)
            if not self._cancelled.is_set():
                self.signals.result.emit(result)
        except OperationCancelled:
            LOGGER.info("Background operation cancelled")
        except Exception as exc:
            LOGGER.exception("Background operation failed")
            self.signals.error.emit(str(exc) or type(exc).__name__)
        finally:
            self.signals.finished.emit()


class TaskManager(QObject):
    """Own background workers and expose one cancellable foreground task."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._workers: set[Worker] = set()
        self.foreground: Worker | None = None

    def start(
        self,
        function: TaskFunction,
        on_result: Callable[[Any], None],
        on_error: Callable[[str], None],
        on_finished: Callable[[], None],
        *,
        foreground: bool = True,
    ) -> Worker:
        worker = Worker(function)
        self._workers.add(worker)
        if foreground:
            self.foreground = worker
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)

        def finish() -> None:
            self._workers.discard(worker)
            if self.foreground is worker:
                self.foreground = None
            on_finished()

        worker.signals.finished.connect(finish)
        self._pool.start(worker)
        return worker

    def cancel_foreground(self) -> None:
        if self.foreground:
            self.foreground.cancel()

    def cancel_all(self) -> None:
        for worker in tuple(self._workers):
            worker.cancel()

    @property
    def active_count(self) -> int:
        return len(self._workers)
