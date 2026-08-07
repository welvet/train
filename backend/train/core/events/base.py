from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Event:
    timestamp: float = field(default_factory=time.time)
