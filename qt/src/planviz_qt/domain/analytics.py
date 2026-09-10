"""Indexed, GUI-independent event history, task state, and productivity queries.

Queries are based on recorded plan time, so seeking backwards has exactly the
same result as opening the plan at that time. A final stop counts both as an
errand completion and as a task completion, but has one row in event history.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
import heapq
import math
from typing import Callable, Iterable

import numpy as np

from .models import Event, PlanData, Task


METRICS = ("assigned", "errand_finished", "task_finished")
_METRIC_ALIASES = {"task": "task_finished", "errand": "errand_finished",
                   "assignments": "assigned"}


class AnalyticsIndex:
    """Build sorted indexes once; normal time queries use binary search.

    ``counts`` returns cumulative counts through and including ``time``.
    ``recent_events`` returns newest-first Event objects, with no future events.
    Empty ``selected_agents`` means all agents for task display; an explicitly
    empty ``agent_ids`` history filter means no agents.
    """

    def __init__(self, plan: PlanData, cancelled: Callable[[], bool] | None = None) -> None:
        def check_cancelled():
            if cancelled is not None and cancelled():
                raise InterruptedError("Analytics indexing cancelled")

        check_cancelled()
        self.plan = plan
        self.tasks = {task.id: task for task in plan.tasks}
        self.events = tuple(sorted(plan.events, key=lambda event: (
            event.time, event.task_id, event.agent_id, event.kind,
            -1 if event.stop_index is None else event.stop_index)))
        check_cancelled()
        self._event_times = tuple(event.time for event in self.events)
        agent_events: dict[int, list[int]] = defaultdict(list)
        location_events: dict[tuple[int, int], list[int]] = defaultdict(list)
        counts: dict[str, dict[int, int]] = {metric: defaultdict(int) for metric in METRICS}
        for index, event in enumerate(self.events):
            if index % 1024 == 0:
                check_cancelled()
            agent_events[event.agent_id].append(index)
            if event.kind in counts:
                counts[event.kind][event.time] += 1
            if event.kind == "task_finished":
                counts["errand_finished"][event.time] += 1
            task = self.tasks.get(event.task_id)
            if task is not None:
                stops = task.stops
                if event.stop_index is not None and 0 <= event.stop_index < len(stops):
                    stops = (stops[event.stop_index],)
                for location in set((int(row), int(col)) for row, col in stops):
                    location_events[location].append(index)
        self._agent_events = {key: tuple(value) for key, value in agent_events.items()}
        self._location_events = {key: tuple(value) for key, value in location_events.items()}
        self._metric_times: dict[str, np.ndarray] = {}
        self._metric_totals: dict[str, np.ndarray] = {}
        self._metric_values: dict[str, np.ndarray] = {}
        self._metric_prefix: dict[str, np.ndarray] = {}
        for metric, by_time in counts.items():
            check_cancelled()
            times = np.asarray(sorted(by_time), dtype=np.int64)
            values = np.asarray([by_time[int(time)] for time in times], dtype=np.int64)
            self._metric_times[metric] = times
            self._metric_values[metric] = values
            self._metric_totals[metric] = np.cumsum(values)
            self._metric_prefix[metric] = np.r_[0, self._metric_totals[metric]]

        released = sorted((task.release_time, task.id) for task in plan.tasks)
        self._released_times = tuple(item[0] for item in released)
        self._released_task_ids = tuple(item[1] for item in released)
        self._assignments: dict[int, tuple[tuple[int, int], ...]] = {}
        self._assignment_times: dict[int, tuple[int, ...]] = {}
        self._completion_times: dict[int, tuple[float, ...]] = {}
        self._task_transition_times: dict[int, tuple[int, ...]] = {}
        self._task_assignment_instants: dict[int, frozenset[int]] = {}
        self._task_templates: dict[int, tuple[dict, ...]] = {}
        all_transitions: set[int] = set()
        all_assignment_instants: set[int] = set()
        by_agent: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for task_number, task in enumerate(plan.tasks):
            if task_number % 1024 == 0:
                check_cancelled()
            assignments = tuple(sorted(task.assignments))
            self._assignments[task.id] = assignments
            self._assignment_times[task.id] = tuple(item[0] for item in assignments)
            for at, agent in assignments:
                by_agent[agent].append((at, task.id))
            completion_times = [math.inf] * len(task.stops)
            for at, _agent, stop in task.completions:
                if 0 <= stop < len(completion_times):
                    completion_times[stop] = min(completion_times[stop], at)
            self._completion_times[task.id] = tuple(completion_times)
            assignment_instants = frozenset(at for at, _agent in assignments)
            transitions = {task.release_time, *assignment_instants,
                           *(at for at, _agent, _stop in task.completions)}
            self._task_assignment_instants[task.id] = assignment_instants
            self._task_transition_times[task.id] = tuple(sorted(transitions))
            self._task_templates[task.id] = tuple(
                {"row": row, "col": col, "label": f"{task.id}:{stop}",
                 "task_id": task.id, "stop_index": stop,
                 "release_time": task.release_time,
                 "kind": "task" if stop == len(task.stops) - 1 else "errand"}
                for stop, (row, col) in enumerate(task.stops))
            all_transitions.update(transitions)
            all_assignment_instants.update(assignment_instants)
        self._agent_assignments = {agent: tuple(sorted(records))
                                   for agent, records in by_agent.items()}
        self._agent_assignment_times = {
            agent: tuple(record[0] for record in records)
            for agent, records in self._agent_assignments.items()
        }
        self._agent_task_history = {
            agent: (self._agent_assignment_times[agent], tuple(task_id for _at, task_id in records))
            for agent, records in self._agent_assignments.items()
        }
        self._task_changes = tuple(sorted(all_transitions))
        self._assignment_instants = frozenset(all_assignment_instants)
        # Cache one current state per task. Most tasks do not change on a given
        # tick, so their marker dictionaries can be reused across scene updates.
        self._task_marker_cache: dict[int, tuple] = {}
        self._marker_key: tuple | None = None
        self._marker_cache: list[dict] = []
        self._series_cache: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}
        check_cancelled()

    def _metric(self, metric: str) -> str:
        metric = _METRIC_ALIASES.get(metric, metric)
        if metric not in METRICS:
            raise ValueError(f"Unknown metric {metric!r}; choose from {METRICS}")
        return metric

    def _cumulative(self, metric: str, times: np.ndarray) -> np.ndarray:
        indices = np.searchsorted(self._metric_times[metric], times, side="right")
        return self._metric_prefix[metric][indices]

    def counts(self, time: float) -> dict[str, int]:
        return {metric: int(self._cumulative(metric, np.asarray([time]))[0])
                for metric in METRICS}

    def series(self, metric: str, mode: str = "cumulative", start: int = 0,
               end: int | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Return a sparse exact cumulative/instant series or average throughput.

        Throughput follows the original viewer: cumulative count divided by
        elapsed ticks/steps since ``start`` (zero at the start). Counts already
        present at ``start`` are retained. Instant series include zero-valued
        neighbours of event times, avoiding false nonzero plateaus across gaps.
        Returned cached arrays are read-only.
        """
        metric = self._metric(metric)
        mode = {"accumulated": "cumulative", "rate": "throughput"}.get(mode, mode)
        if mode not in {"cumulative", "instant", "throughput"}:
            raise ValueError(f"Unknown series mode: {mode!r}")
        start = int(start)
        end = int(self.plan.max_time if end is None else end)
        if end < start:
            raise ValueError("Series end cannot precede start")
        key = (metric, mode, start, end)
        if key in self._series_cache:
            return self._series_cache[key]
        times = self._metric_times[metric]
        left, right = np.searchsorted(times, (start, end), side="right")
        x = np.unique(np.r_[start, times[left:right], end]).astype(np.int64)
        if mode == "instant":
            # Include boundary events as well as transitions back to zero.
            event_times = times[(times >= start) & (times <= end)]
            x = np.unique(np.r_[x, event_times - 1, event_times, event_times + 1])
            x = x[(x >= start) & (x <= end)]
            indices = np.searchsorted(times, x)
            y = np.zeros(x.shape, dtype=np.int64)
            valid = indices < len(times)
            matches = np.zeros(x.shape, dtype=bool)
            matches[valid] = times[indices[valid]] == x[valid]
            y[matches] = self._metric_values[metric][indices[matches]]
        else:
            y = self._cumulative(metric, x)
            if mode == "throughput":
                # A bounded regular sample also shows the rate falling between
                # sparse completions without allocating max_time-sized arrays.
                x = np.unique(np.r_[x, np.linspace(start, end,
                                      min(2001, end - start + 1), dtype=np.int64)])
                cumulative = self._cumulative(metric, x)
                y = np.divide(cumulative, x - start,
                              out=np.zeros(len(x), dtype=float), where=x > start)
        x.setflags(write=False)
        y.setflags(write=False)
        # Full-range series dominate playback; bounded cache also handles seeks.
        if len(self._series_cache) >= 24:
            self._series_cache.pop(next(iter(self._series_cache)))
        self._series_cache[key] = (x, y)
        return x, y

    def recent_events(self, time: float, limit: int,
                      agent_ids: Iterable[int] | None = None,
                      location: tuple[int, int] | None = None) -> list[Event]:
        if limit <= 0:
            return []
        agents = None if agent_ids is None else frozenset(agent_ids)
        if agents is not None and not agents:
            return []
        end = bisect_right(self._event_times, time)
        if location is not None:
            source = self._location_events.get(tuple(location), ())
            candidates = self._reverse_indices(source, end)
        elif agents is not None:
            sources = []
            for agent in agents:
                source = self._agent_events.get(agent, ())
                sources.append(self._reverse_indices(source, end))
            candidates = heapq.merge(*sources, reverse=True)
        else:
            candidates = range(end - 1, -1, -1)
        result = []
        for index in candidates:
            event = self.events[index]
            if agents is None or event.agent_id in agents:
                result.append(event)
                if len(result) == limit:
                    break
        return result

    @staticmethod
    def _reverse_indices(source: tuple[int, ...], end: int):
        # Do not copy a potentially million-row history just to show 100 rows.
        for position in range(bisect_right(source, end - 1) - 1, -1, -1):
            yield source[position]

    def _owner(self, task_id: int, time: float) -> tuple[int | None, float]:
        index = bisect_right(self._assignment_times[task_id], time) - 1
        if index < 0:
            return None, -math.inf
        assigned_at, agent = self._assignments[task_id][index]
        return agent, assigned_at

    def active_task_context(self, time: float, agent: int) -> dict | None:
        records = self._agent_assignments.get(agent, ())
        index = bisect_right(self._agent_assignment_times.get(agent, ()), time) - 1
        if index < 0:
            return None
        _assigned_at, task_id = records[index]
        next_assignment_time = records[index + 1][0] if index + 1 < len(records) else None
        task = self.tasks[task_id]
        owner, assigned_at = self._owner(task_id, time)
        if owner != agent or time < task.release_time:
            return None
        completed = tuple(stop for stop, at in enumerate(self._completion_times[task_id])
                          if at <= time)
        remaining = tuple(stop for stop, at in enumerate(self._completion_times[task_id])
                          if at > time)
        next_stop_index = remaining[0] if remaining else None
        return {"task_id": task_id, "task": task, "agent_id": agent,
                "assigned_at": assigned_at, "completed_stops": completed,
                "remaining_stops": tuple(task.stops[stop] for stop in remaining),
                "next_stop_index": next_stop_index,
                "next_assignment_time": next_assignment_time,
                "next_stop": task.stops[next_stop_index] if remaining else None,
                "state": "assigned" if remaining else "finished"}

    def next_recorded_errand(self, time: float, agent: int) -> dict | None:
        """Find a future completion for path preview, without inferring ownership.

        Some logs omit initial assignments or give them invalid timestamps.
        Completion records can still identify a path endpoint; they must not
        be turned into invented assignment events or active-task states.
        """
        indices = self._agent_events.get(agent, ())
        first_event = bisect_right(self._event_times, time) - 1
        start = bisect_right(indices, first_event)
        for offset in range(start, len(indices)):
            event = self.events[indices[offset]]
            if event.kind not in ("errand_finished", "task_finished"):
                continue
            task = self.tasks.get(event.task_id)
            if task is not None and event.stop_index is not None and 0 <= event.stop_index < len(task.stops):
                return {"next_stop": task.stops[event.stop_index], "completion_time": event.time}
        return None

    def task_markers(self, time: float, mode: str = "all",
                     selected_agents: Iterable[int] = ()) -> list[dict]:
        mode = {"All Tasks": "all", "Assigned Tasks": "assigned",
                "Next Errand": "next"}.get(mode, mode)
        if mode == "none":
            return []
        if mode not in {"all", "assigned", "next"}:
            raise ValueError(f"Unknown task display mode: {mode!r}")
        selected = frozenset(selected_agents)
        key = (bisect_right(self._task_changes, time),
               time in self._assignment_instants, mode, selected)
        if key == self._marker_key:
            return self._marker_cache
        if mode == "all":
            end = bisect_right(self._released_times, time)
            task_ids = self._released_task_ids[:end]
            markers = []
            for task_id in task_ids:
                _state_key, owner, all_markers, _assigned, _next = self._task_display_state(task_id, time)
                if not selected or owner in selected:
                    markers.extend(all_markers)
        else:
            markers = []
            seen_tasks = set()
            histories = ((agent, self._agent_task_history.get(agent, ((), ()))) for agent in selected) \
                if selected else self._agent_task_history.items()
            for agent, (assignment_times, assigned_tasks) in histories:
                at = bisect_right(assignment_times, time) - 1
                if at < 0:
                    continue
                task_id = assigned_tasks[at]
                if task_id in seen_tasks or time < self.tasks[task_id].release_time:
                    continue
                _state_key, owner, _all, assigned_markers, next_markers = self._task_display_state(task_id, time)
                if owner != agent:
                    continue
                seen_tasks.add(task_id)
                markers.extend(next_markers if mode == "next" else assigned_markers)
        self._marker_key, self._marker_cache = key, markers
        return markers

    def _task_display_state(self, task_id: int, time: float) -> tuple:
        """Reuse marker dictionaries until this task changes state.

        The exact-assignment flag matters for the one-tick newly-assigned color,
        including callers that query fractional times immediately afterward.
        """
        key = (bisect_right(self._task_transition_times[task_id], time),
               time in self._task_assignment_instants[task_id])
        cached = self._task_marker_cache.get(task_id)
        if cached is not None and cached[0] == key:
            return cached
        owner, assigned_at = self._owner(task_id, time)
        all_markers, assigned_markers = [], []
        for template, completed_at in zip(self._task_templates[task_id], self._completion_times[task_id]):
            finished = completed_at <= time
            state = ("finished" if finished else "unassigned" if owner is None
                     else "newlyassigned" if assigned_at == time else "assigned")
            marker = dict(template, state=state, agent_id=owner)
            all_markers.append(marker)
            if not finished and owner is not None:
                assigned_markers.append(marker)
        assigned = tuple(assigned_markers)
        cached = (key, owner, tuple(all_markers), assigned, assigned[:1])
        self._task_marker_cache[task_id] = cached
        return cached
