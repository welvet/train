from __future__ import annotations

import asyncio
import logging
import weakref
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from train.domain import CommandSpec, Event, SystemState, command_spec

E = TypeVar("E", bound=Event)
EventHandler = Callable[[Any], Coroutine[Any, Any, None]]
DEFAULT_COMMAND_TIMEOUT = 3.0


class UnsupportedCommand(ValueError):
    pass


class CommandFailed(RuntimeError):
    def __init__(self, command: Event, response: Event) -> None:
        super().__init__(f"{type(command).__name__} failed")
        self.command = command
        self.response = response


class CommandResourceNotFound(LookupError):
    def __init__(self, command: Event, message: str) -> None:
        super().__init__(message)
        self.command = command


class EventBus:
    def __init__(self, state: SystemState | None = None) -> None:
        self._handlers: dict[type[Event], list[EventHandler]] = defaultdict(list)
        self._log = logging.getLogger("train.event_bus")
        self._state = state.snapshot() if state is not None else SystemState()
        self._command_locks: weakref.WeakValueDictionary[
            tuple[str, ...], asyncio.Lock
        ] = weakref.WeakValueDictionary()

    @property
    def state(self) -> SystemState:
        """Return an isolated snapshot of the canonical domain state."""
        return self._state.snapshot()

    def subscribe(self, event_type: type[E], handler: Callable[[E], Coroutine[Any, Any, None]]) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[E], handler: Callable[[E], Coroutine[Any, Any, None]]) -> None:
        self._handlers[event_type].remove(handler)

    async def publish(self, event: Event) -> None:
        self._log.debug("Event: %s", event)
        self._state.apply(event)
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

    async def dispatch(
        self,
        command: Event,
        *,
        timeout: float = DEFAULT_COMMAND_TIMEOUT,
    ) -> Event | None:
        spec = command_spec(command)
        if spec is None:
            raise UnsupportedCommand(type(command).__name__)
        missing_resource = spec.missing_resource(command, self._state)
        if missing_resource is not None:
            raise CommandResourceNotFound(command, missing_resource)
        resource = spec.resource_key(command)
        lock = self._command_locks.setdefault(resource, asyncio.Lock())
        async with asyncio.timeout(timeout):
            async with lock:
                return await self._dispatch_locked(command, spec)

    async def _dispatch_locked(
        self, command: Event, spec: CommandSpec
    ) -> Event | None:
        if spec.response_type is None:
            await self.publish(command)
            return None

        if spec.response_matches is None or spec.response_succeeded is None:
            raise RuntimeError(
                f"Incomplete command specification for {type(command).__name__}"
            )

        response: asyncio.Future[Event] = asyncio.get_running_loop().create_future()

        async def on_response(event: Event) -> None:
            if spec.response_matches(command, event) and not response.done():
                response.set_result(event)

        async def publish_and_wait() -> Event:
            await self.publish(command)
            return await response

        self.subscribe(spec.response_type, on_response)
        try:
            result = await publish_and_wait()
        finally:
            self.unsubscribe(spec.response_type, on_response)

        if not spec.response_succeeded(result):
            raise CommandFailed(command, result)
        return result
