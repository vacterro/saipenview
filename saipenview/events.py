"""Lightweight in-process event bus.

Simple pub/sub for decoupling agent lifecycle events from the UI
update layer.  No external dependencies, no serialization, no
network -- just callbacks on the same process.

Usage::

    from saipenview.events import event_bus

    def on_agent_output(data):
        print(data["root"], data["line"])

    event_bus.subscribe("agent.output", on_agent_output)
    event_bus.publish("agent.output", {"root": "/foo", "line": "hello"})
"""

from __future__ import annotations

import sys
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any


class EventBus:
    """Thread-safe publish/subscribe event dispatcher."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(
        self, event_type: str, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a callback for an event type.

        Args:
            event_type: Event name, e.g. 'agent.started', 'agent.output'.
            callback: Function(data: dict) to invoke when event fires.
        """
        with self._lock:
            self._subscribers[event_type].append(callback)

    def has_subscribers(self, event_type: str) -> bool:
        """True when at least one callback is registered for *event_type*.

        Publishers of high-frequency events (per-line agent output) use this
        to skip payload construction entirely when nobody is listening --
        building a dict nobody receives is pure waste (T-598/PERF-009).
        """
        with self._lock:
            return bool(self._subscribers.get(event_type))

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """Remove a previously registered callback."""
        with self._lock:
            subs = self._subscribers.get(event_type)
            if subs:
                try:
                    subs.remove(callback)
                except ValueError:
                    pass

    def publish(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Fire an event, calling all subscribers synchronously.

        Subscriber exceptions are caught and logged to stderr --
        a broken subscriber must never kill the publisher.

        Args:
            event_type: Event name to dispatch.
            data: Payload dict passed to each subscriber.
        """
        with self._lock:
            subs = list(self._subscribers.get(event_type, []))
        payload = data or {}
        for cb in subs:
            try:
                cb(payload)
            except Exception as exc:  # noqa: BLE001 - user callback failure
                print(
                    f"SAIPENVIEW: event subscriber for '{event_type}' failed: {exc}",
                    file=sys.stderr,
                )

    def clear(self) -> None:
        """Remove all subscribers.  Used for shutdown/testing."""
        with self._lock:
            self._subscribers.clear()


# Module-level singleton -- import and use directly.
event_bus = EventBus()
