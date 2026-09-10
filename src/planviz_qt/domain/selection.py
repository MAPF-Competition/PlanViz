"""Bounded, reusable next-errand path previews, independent of Qt.

Samples are consecutive logical states. Only exactly straight or stationary
interior vertices are removed; no shortcut is drawn across a turn. A moving
window reuses fixed blocks rather than decoding a new trajectory every tick.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field

import numpy as np

from .analytics import AnalyticsIndex
from .models import PlanData


@dataclass(frozen=True)
class SelectedPath:
    agent: int
    start: int
    end: int
    points: np.ndarray
    geometry_key: tuple
    source: str = "assignment"

    @property
    def has_movement(self):
        return len(self.points) > 1


@dataclass
class _Block:
    serial: int
    start: int
    actual: np.ndarray
    planned: np.ndarray | None = None
    corners: dict = field(default_factory=dict)


class SelectedPathService:
    def __init__(self, plan: PlanData, analytics: AnalyticsIndex, *, max_states=2000,
                 block_size=256, cache_size=128):
        if max_states < 2 or block_size < 1 or cache_size < 1:
            raise ValueError("Path window, block, and cache sizes must be positive (at least two states).")
        self.plan, self.analytics = plan, analytics
        self.max_states, self.block_size, self.cache_size = max_states, block_size, cache_size
        self._blocks = OrderedDict()
        self._arrivals = OrderedDict()
        self._serial = 0

    @property
    def cache_entries(self):
        return len(self._blocks)

    @property
    def cache_bytes(self):
        return sum(block.actual.nbytes + (block.planned.nbytes if block.planned is not None else 0)
                   + sum(corners.nbytes for corners in block.corners.values())
                   for block in self._blocks.values()) + sum(a.nbytes for a in self._arrivals.values())

    def _block(self, agent, time):
        start = time // self.block_size * self.block_size
        key = agent, start
        if key not in self._blocks:
            end = min(self.plan.max_time, start + self.block_size + self.max_states - 2)
            points = self.plan.paths.trajectory(agent, start, end, max_points=max(2, end-start+1))
            points.setflags(write=False)
            self._serial += 1
            self._blocks[key] = _Block(self._serial, start, points)
            if len(self._blocks) > self.cache_size:
                self._blocks.popitem(last=False)
        self._blocks.move_to_end(key)
        return self._blocks[key]

    def _target(self, time, agent, horizon):
        context = self.analytics.active_task_context(time, agent)
        if context and context["next_stop"] is not None:
            task = context["task"]
            bounds = [horizon]
            if context["next_assignment_time"] is not None:
                bounds.append(context["next_assignment_time"])
            bounds.extend(at for at, _owner, stop in task.completions
                          if stop == context["next_stop_index"] and at >= time)
            bounds.extend(at for at, _owner in task.assignments if at > time)
            return context["next_stop"], min(bounds), "assignment"
        recorded = self.analytics.next_recorded_errand(time, agent)
        if recorded:
            return recorded["next_stop"], min(horizon, recorded["completion_time"]), "completion"
        return None, horizon, "recording"

    def preview(self, agent: int, time: int, end: int, *, planned=False) -> SelectedPath:
        if not 0 <= agent < self.plan.team_size:
            raise IndexError(f"Unknown agent {agent}.")
        time = min(max(int(time), 0), self.plan.max_time)
        horizon = min(self.plan.max_time, max(time, int(end)), time+self.max_states-1)
        target, horizon, source = self._target(time, agent, horizon)
        block = self._block(agent, time)
        if target is not None:
            arrival_key = block.serial, tuple(target)
            if arrival_key not in self._arrivals:
                self._arrivals[arrival_key] = np.flatnonzero(np.all(np.isclose(
                    block.actual[:, :2], target, atol=1e-6, rtol=0), axis=1)) + block.start
                if len(self._arrivals) > self.cache_size:
                    self._arrivals.popitem(last=False)
            self._arrivals.move_to_end(arrival_key)
            arrivals = self._arrivals[arrival_key]
            index = np.searchsorted(arrivals, time)
            if index < len(arrivals):
                horizon = min(horizon, int(arrivals[index]))
        if planned and block.planned is None:
            block.planned = self.plan.paths.trajectory(agent, block.start,
                block.start+len(block.actual)-1, planned=True, max_points=max(2, len(block.actual)))
            block.planned.setflags(write=False)
        values = block.planned if planned else block.actual
        if planned not in block.corners:
            # Keep velocity changes, including waits and reversals. Rounding
            # noise below 1e-9 cells is immaterial; all non-collinear turns stay.
            changes = np.any(np.abs(np.diff(values[:, :2], n=2, axis=0)) > 1e-9, axis=1)
            block.corners[planned] = np.flatnonzero(changes) + 1
        corners = block.corners[planned]
        start_offset, end_offset = time-block.start, horizon-block.start
        left = int(np.searchsorted(corners, start_offset, side="right"))
        right = int(np.searchsorted(corners, end_offset, side="left"))
        offsets = np.r_[start_offset, corners[left:right], end_offset].astype(np.int64)
        points = values[offsets]
        keep = np.r_[True, np.any(np.diff(points[:, :2], axis=0) != 0, axis=1)]
        points = points[keep]
        points.setflags(write=False)
        key = (block.serial, bool(planned), left, right, tuple(np.flatnonzero(keep)))
        return SelectedPath(agent, time, horizon, points, key, source)
