"""Data contracts shared by loaders, playback, and renderers.

Coordinates are always (row, column); orientation 0/1/2/3 is E/N/W/S.
These records contain neither GUI objects nor GUI framework imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .paths import PathStore


@dataclass(frozen=True)
class MapData:
    grid: np.ndarray
    source: str = ""
    name: str = ""

    @property
    def width(self) -> int:
        return int(self.grid.shape[1])

    @property
    def height(self) -> int:
        return int(self.grid.shape[0])


@dataclass(frozen=True)
class Task:
    id: int
    release_time: int
    stops: tuple[tuple[float, float], ...]
    assignments: tuple[tuple[int, int], ...] = ()
    completions: tuple[tuple[int, int, int], ...] = ()

    def assigned_agent(self, time: int) -> int | None:
        """Return the most recent recorded assignment at or before time."""
        result = None
        for assigned_time, agent_id in self.assignments:
            if assigned_time > time:
                break
            result = agent_id
        return result

    def completed_stops(self, time: int) -> frozenset[int]:
        return frozenset(stop for at, _agent, stop in self.completions if at <= time)

    def state(self, time: int) -> str:
        if time < self.release_time:
            return "unreleased"
        if self.stops and len(self.completed_stops(time)) >= len(self.stops):
            return "finished"
        return "assigned" if self.assigned_agent(time) is not None else "unassigned"


@dataclass(frozen=True)
class Event:
    time: int
    agent_id: int
    task_id: int
    kind: str
    stop_index: int | None = None
    id: str = ""


@dataclass(frozen=True)
class Conflict:
    time: int
    agent_ids: tuple[int, ...]
    description: str
    task_id: int | None = None


@dataclass(frozen=True)
class PlanData:
    map: MapData
    paths: PathStore
    tasks: tuple[Task, ...]
    events: tuple[Event, ...]
    conflicts: tuple[Conflict, ...]
    delays: dict[int, tuple[tuple[int, int], ...]]
    metadata: dict
    version: str
    action_model: str
    time_unit: str
    ticks_per_step: int
    max_time: int

    @property
    def team_size(self) -> int:
        return self.paths.team_size

    def delayed_agents(self, time: int) -> frozenset[int]:
        return frozenset(agent for agent, intervals in self.delays.items()
                         if any(start <= time <= end for start, end in intervals))

    def conflict_agents(self, time: int) -> frozenset[int]:
        return frozenset(agent for conflict in self.conflicts if conflict.time == time
                         for agent in conflict.agent_ids)
