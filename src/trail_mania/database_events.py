"""Notify live application listeners after successful database writes."""

import logging
import threading
from pathlib import Path
from typing import Protocol
from weakref import WeakSet


class DatabaseChangeListener(Protocol):
    def database_changed(self, database: Path) -> None: ...


_listeners: WeakSet[DatabaseChangeListener] = WeakSet()
_lock = threading.Lock()
_logger = logging.getLogger(__name__)


def subscribe_database_changes(listener: DatabaseChangeListener) -> None:
    """Observe committed writes without keeping closed application pages alive."""
    with _lock:
        _listeners.add(listener)


def unsubscribe_database_changes(listener: DatabaseChangeListener) -> None:
    """Detach a closed page immediately, including before garbage collection."""
    with _lock:
        _listeners.discard(listener)


def notify_database_changed(database: Path) -> None:
    """Dispatch after commit; a listener failure must not invalidate a saved write."""
    database = database.resolve()
    with _lock:
        listeners = list(_listeners)
    for listener in listeners:
        try:
            listener.database_changed(database)
        except Exception:
            _logger.warning("Could not schedule post-commit database work")
