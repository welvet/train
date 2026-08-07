from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from train.core.events.base import Event

E = TypeVar("E", bound=Event)
EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[EventHandler]] = defaultdict(list)
        self._log = logging.getLogger("train.event_bus")

    def subscribe(self, event_type: type[E], handler: Callable[[E], Coroutine[Any, Any, None]]) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[E], handler: Callable[[E], Coroutine[Any, Any, None]]) -> None:
        self._handlers[event_type].remove(handler)

    async def publish(self, event: Event) -> None:
        self._log.debug("Event: %s", event)
        tasks: list[Coroutine[Any, Any, None]] = []
        for registered_type, handlers in self._handlers.items():
            if isinstance(event, registered_type):
                for handler in handlers:
                    tasks.append(handler(event))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    self._log.error(
                        "Handler error for %s: %s",
                        type(event).__name__,
                        r,
                        exc_info=r,
                    )
