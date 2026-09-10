"""The extension contract; converters know nothing about Qt widgets."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from ..domain.models import MapData, PlanData
from .errors import LoadCancelled


@dataclass(frozen=True)
class ConversionContext:
    map_data: MapData
    source: Path
    team_size: int | None = None
    progress: Callable[[int, str], None] | None = None
    cancelled: Callable[[], bool] | None = None

    def checkpoint(self, percent: int, message: str) -> None:
        if self.cancelled is not None and self.cancelled():
            raise LoadCancelled("Plan loading cancelled.")
        if self.progress is not None:
            self.progress(int(percent), message)


class InputConverter(Protocol):
    """A format detector and decoder registered under a stable ID.

    Detection must inspect structure without mutating its input. Explicit
    selection calls convert directly, so convert must validate its own schema.
    Source-specific coordinate/action conventions belong in this layer.
    """
    id: str
    label: str

    def can_read(self, data: dict) -> bool: ...

    def convert(self, data: dict, context: ConversionContext) -> PlanData: ...
