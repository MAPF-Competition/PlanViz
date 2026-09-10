"""Compressed, vectorized random access to execution and one-step plans.

Storage is proportional to motion runs, not agents multiplied by ticks. Each
run has an analytic start state. A global sorted key permits one NumPy search
for the states of every agent at a requested time.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np


@dataclass(frozen=True)
class MotionSequence:
    actions: tuple[str, ...]
    durations: tuple[int, ...]

    @property
    def length(self) -> int:
        return sum(self.durations)


class PathStore:
    def __init__(self, starts: np.ndarray, actual: Sequence[MotionSequence],
                 planned: Sequence[MotionSequence] | None = None, *,
                 action_model: str = "MAPF_T", ticks_per_step: int = 1,
                 max_time: int | None = None, cache_size: int = 4,
                 cancelled: Callable[[], bool] | None = None):
        starts = np.asarray(starts, dtype=np.float64)
        if starts.ndim != 2 or starts.shape[1] != 3:
            raise ValueError("starts must have shape (agent_count, 3).")
        if len(actual) != len(starts):
            raise ValueError("Each agent must have an actual motion sequence.")
        if planned is None:
            planned = actual
        if len(planned) != len(starts):
            raise ValueError("Each agent must have a planned motion sequence.")
        if ticks_per_step <= 0:
            raise ValueError("ticks_per_step must be positive.")
        if action_model not in {"MAPF", "MAPF_T"}:
            raise ValueError(f"Unsupported action_model {action_model!r}.")
        self._starts = starts.copy()
        self._starts.flags.writeable = False
        self.action_model = action_model
        self.ticks_per_step = int(ticks_per_step)
        self._actual_lengths = np.asarray([s.length for s in actual], dtype=np.int64)
        self._planned_lengths = np.asarray([s.length for s in planned], dtype=np.int64)
        path_max = max(int(self._actual_lengths.max(initial=0)),
                       int(self._planned_lengths.max(initial=0)))
        self._max_time = max(path_max, int(max_time or 0))
        self._stride = self._max_time + 1
        if self._stride * max(1, self.team_size) >= np.iinfo(np.int64).max:
            raise ValueError("Plan time range is too large to index.")
        self._ids = np.arange(self.team_size, dtype=np.int64)
        self._actual = self._build_table(actual, True, cancelled)
        self._planned = self._actual if planned is actual else self._build_table(planned, False, cancelled)
        self._cache: OrderedDict[tuple[int, bool], np.ndarray] = OrderedDict()
        self._cache_size = max(1, int(cache_size))

    @property
    def starts(self) -> np.ndarray:
        return self._starts

    @property
    def team_size(self) -> int:
        return len(self._starts)

    @property
    def max_time(self) -> int:
        return self._max_time

    def iter_motion_sequences(self, planned: bool = False):
        """Yield compressed runs for each agent without reconstructing ticks.

        Run tables already retain action codes and boundaries, so exporting a
        plan needs neither a second stored motion history nor dense snapshots.
        The terminal wait sentinel is an index detail and is not exported.
        """
        table = self._planned if planned else self._actual
        for agent in range(self.team_size):
            first, last = np.searchsorted(
                table["keys"], (agent * self._stride, (agent + 1) * self._stride))
            yield MotionSequence(
                tuple(chr(int(code)) for code in table["codes"][first:last - 1]),
                tuple(int(value) for value in np.diff(table["times"][first:last])),
            )

    @property
    def storage_bytes(self) -> int:
        tables = [self._actual] if self._actual is self._planned else [self._actual, self._planned]
        return (self._starts.nbytes + self._actual_lengths.nbytes + self._planned_lengths.nbytes
                + sum(a.nbytes for table in tables for a in table.values())
                + sum(a.nbytes for a in self._cache.values()))

    def _build_table(self, sequences, include_states, cancelled):
        keys, times, codes, states = [], [], [], []
        for agent, sequence in enumerate(sequences):
            if cancelled is not None and cancelled():
                raise InterruptedError("Plan loading cancelled.")
            durations = np.asarray(sequence.durations, dtype=np.int64)
            if len(durations) != len(sequence.actions) or np.any(durations <= 0):
                raise ValueError(f"Agent {agent} has invalid motion runs.")
            ends = np.cumsum(durations, dtype=np.int64)
            run_times = np.concatenate((np.zeros(1, dtype=np.int64), ends))
            actions = np.asarray([ord(a) for a in sequence.actions] + [ord("W")], dtype=np.uint8)
            keys.append(agent * self._stride + run_times)
            times.append(run_times)
            codes.append(actions)
            if include_states:
                # Every run holds a constant action. Its endpoint follows from
                # duration and its start orientation, without expanding ticks.
                rotation = np.zeros(len(actions), dtype=np.float64)
                if self.action_model != "MAPF":
                    rotation[:-1] = ((actions[:-1] == ord("C")).astype(np.int8)
                                     - (actions[:-1] == ord("R")).astype(np.int8)) * durations / self.ticks_per_step
                orientation = (self._starts[agent, 2] + np.concatenate(([0.0], np.cumsum(rotation[:-1])))) % 4.0
                if self.action_model == "MAPF":
                    orientation[:] = self._starts[agent, 2]
                    dr = ((actions[:-1] == ord("U")).astype(np.int8)
                          - (actions[:-1] == ord("D")).astype(np.int8)) * durations / self.ticks_per_step
                    dc = ((actions[:-1] == ord("R")).astype(np.int8)
                          - (actions[:-1] == ord("L")).astype(np.int8)) * durations / self.ticks_per_step
                else:
                    distance = (actions[:-1] == ord("F")) * durations / self.ticks_per_step
                    angle = orientation[:-1] * np.pi / 2.0
                    dr, dc = -np.sin(angle) * distance, np.cos(angle) * distance
                coords = np.empty((len(actions), 3), dtype=np.float64)
                coords[:, 0] = self._starts[agent, 0] + np.concatenate(([0.0], np.cumsum(dr)))
                coords[:, 1] = self._starts[agent, 1] + np.concatenate(([0.0], np.cumsum(dc)))
                coords[:, 2] = orientation
                states.append(coords)
        table = {"keys": np.concatenate(keys) if keys else np.empty(0, np.int64),
                 "times": np.concatenate(times) if times else np.empty(0, np.int64),
                 "codes": np.concatenate(codes) if codes else np.empty(0, np.uint8)}
        if include_states:
            table["states"] = np.concatenate(states) if states else np.empty((0, 3), np.float64)
        return table

    def _advance(self, states, codes, duration):
        result = states.copy()
        distance = np.asarray(duration, dtype=np.float64) / self.ticks_per_step
        if self.action_model == "MAPF":
            result[:, 0] += ((codes == ord("U")).astype(np.int8) - (codes == ord("D")).astype(np.int8)) * distance
            result[:, 1] += ((codes == ord("R")).astype(np.int8) - (codes == ord("L")).astype(np.int8)) * distance
        else:
            forward = (codes == ord("F")) * distance
            angle = result[:, 2] * np.pi / 2.0
            result[:, 0] -= np.sin(angle) * forward
            result[:, 1] += np.cos(angle) * forward
            result[:, 2] = (result[:, 2] + ((codes == ord("C")).astype(np.int8)
                               - (codes == ord("R")).astype(np.int8)) * distance) % 4.0
        return result

    def _actual_at(self, agent_ids, times):
        times = np.minimum(np.maximum(times, 0), self._actual_lengths[agent_ids])
        table = self._actual
        idx = np.searchsorted(table["keys"], agent_ids * self._stride + times, side="right") - 1
        return self._advance(table["states"][idx], table["codes"][idx], times - table["times"][idx])

    def _positions_at(self, agent_ids, times, planned):
        if not len(agent_ids):
            return np.empty((0, 3), dtype=np.float64)
        if not planned:
            return self._actual_at(agent_ids, times)
        times = np.minimum(np.maximum(times, 0), self._planned_lengths[agent_ids])
        previous = np.maximum(times - 1, 0)
        actual = self._actual_at(agent_ids, previous)
        idx = np.searchsorted(self._planned["keys"], agent_ids * self._stride + previous, side="right") - 1
        result = self._advance(actual, self._planned["codes"][idx], (times > 0).astype(np.int64))
        result[times == 0] = self._starts[agent_ids[times == 0]]
        return result

    def positions(self, time: int, planned: bool = False) -> np.ndarray:
        """Return an immutable N×3 snapshot, clamping finished agents in place."""
        time = min(max(int(time), 0), self._max_time)
        key = (time, bool(planned))
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        result = np.round(self._positions_at(self._ids, np.full(self.team_size, time, np.int64), planned), 6)
        result.flags.writeable = False
        self._cache[key] = result
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return result

    def trajectory(self, agent_id: int, start: int, end: int, planned: bool = False,
                   max_points: int = 2000) -> np.ndarray:
        """Sample one agent's inclusive time range with a bounded point count."""
        if not 0 <= agent_id < self.team_size:
            raise IndexError(f"Unknown agent {agent_id}.")
        if max_points < 2:
            raise ValueError("max_points must be at least 2.")
        start = min(max(int(start), 0), self._max_time)
        end = min(max(int(end), start), self._max_time)
        count = min(end - start + 1, int(max_points))
        times = np.unique(np.linspace(start, end, count, dtype=np.int64))
        return np.round(self._positions_at(np.full(len(times), agent_id, np.int64), times, planned), 6)
