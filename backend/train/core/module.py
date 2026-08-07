from __future__ import annotations

from abc import ABC, abstractmethod

from train.core.event_bus import EventBus


class Module(ABC):
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.name = self.__class__.__name__

    @abstractmethod
    async def start(self) -> None: ...

    async def stop(self) -> None:
        pass

    def __repr__(self) -> str:
        return f"<Module {self.name}>"
