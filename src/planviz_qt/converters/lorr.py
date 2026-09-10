"""LoRR version adapters sharing one normalized task/motion implementation."""
from __future__ import annotations

import numpy as np

from ..domain.models import Conflict, Event, PlanData, Task
from ..domain.paths import PathStore
from .motions import parse_motion_sequence
from .base import ConversionContext


VERSIONS = ("2023 LoRR", "2024 LoRR", "2026 LoRR")

def _integer(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}.")
    return value


def normalize_version(value):
    if value in ("2023", "2024", "2026"):
        return value + " LoRR"
    return value


def detect_version(data: dict) -> str | None:
    if data.get("format") not in (None, "lorr"):
        return None
    explicit = normalize_version(data.get("version"))
    if explicit:
        return explicit if explicit in VERSIONS else None
    if not isinstance(data.get("start"), list):
        return None
    if not any(key in data for key in ("actionModel", "actualPaths", "teamSize")):
        return None
    paths = data.get("actualPaths") or []
    if ("makespanTicks" in data or "agentMaxCounter" in data or
            any(isinstance(path, str) and path.lstrip().startswith("[(") for path in paths)):
        return "2026 LoRR"
    tasks = data.get("tasks") or []
    if ("actualSchedule" in data or "scheduleErrors" in data or
            any(isinstance(task, list) and len(task) == 3 and isinstance(task[2], list) for task in tasks)):
        return "2024 LoRR"
    return "2023 LoRR"


def _merge_intervals(intervals):
    merged = []
    for start, end in sorted((min(int(a), int(b)), max(int(a), int(b))) for a, b in intervals):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return tuple(merged)


def _decode_lorr(data: dict, context: ConversionContext, selected_version: str) -> PlanData:
    map_data, source = context.map_data, context.source
    team_size, cancelled = context.team_size, context.cancelled
    checkpoint = context.checkpoint
    if data.get("format") not in (None, "lorr"):
        raise ValueError("A LoRR converter cannot read another format's document.")
    if selected_version != "2026 LoRR":
        for field in ("actualPaths", "plannerPaths"):
            if any(isinstance(path, str) and path.lstrip().startswith("[(")
                   for path in data.get(field) or []):
                raise ValueError("Segmented RLE paths require the LoRR 2026 converter and tick time units.")
    action_model = data.get("actionModel", "MAPF_T")
    if action_model not in {"MAPF", "MAPF_T"}:
        raise ValueError(f"Unsupported actionModel {action_model!r}.")
    tick = selected_version == "2026 LoRR"
    ticks = _integer(data.get("agentMaxCounter", 10), "agentMaxCounter", 1) if tick else 1
    if ticks <= 0:
        raise ValueError("agentMaxCounter must be positive.")
    declared = _integer(data.get("teamSize", len(data.get("start", []))), "teamSize")
    if declared < 0 or (team_size is not None and int(team_size) < 0):
        raise ValueError("teamSize must not be negative.")
    count = declared if team_size is None else min(declared, int(team_size))
    raw_starts = data.get("start", [])
    if not isinstance(raw_starts, list) or len(raw_starts) < count:
        raise ValueError(f"start must contain at least {count} agent states.")
    direction = {"E": 0, "N": 1, "W": 2, "S": 3, "N/A": -1}
    starts = np.empty((count, 3), dtype=np.float64)
    for agent, state in enumerate(raw_starts[:count]):
        if not isinstance(state, list) or len(state) < 3:
            raise ValueError(f"start[{agent}] must be [row, column, direction].")
        orientation = direction[state[2]] if isinstance(state[2], str) else float(state[2])
        starts[agent] = (float(state[0]), float(state[1]), orientation)
        if not np.all(np.isfinite(starts[agent])):
            raise ValueError(f"start[{agent}] contains a non-finite coordinate.")
    fields = data.get("actualPaths")
    if "actualPaths" not in data and selected_version == "2023 LoRR":
        # Legacy 2023 permits a static start-only result without execution.
        fields = [""] * count
    if not isinstance(fields, list) or len(fields) < count:
        raise ValueError(f"actualPaths must contain at least {count} paths.")
    planned_fields = data.get("plannerPaths")
    if planned_fields is not None and (not isinstance(planned_fields, list) or len(planned_fields) < count):
        raise ValueError(f"plannerPaths must contain at least {count} paths when provided.")
    actual, planned = [], []
    for agent in range(count):
        if agent % 64 == 0:
            checkpoint(15 + 45 * agent // max(count, 1), f"Decoding agent {agent + 1}/{count}")
        actual.append(parse_motion_sequence(fields[agent], tick=tick, action_model=action_model,
                                            label=f"actualPaths[{agent}]"))
        if planned_fields is not None:
            planned.append(parse_motion_sequence(planned_fields[agent], tick=tick, action_model=action_model,
                                                 label=f"plannerPaths[{agent}]"))
    declared_time = data.get("makespanTicks") if tick else None
    if declared_time is None:
        declared_time = data.get("makespan", 0)
    max_time = _integer(declared_time, "makespanTicks" if tick and data.get("makespanTicks") is not None else "makespan")
    checkpoint(62, "Indexing compressed paths")
    paths = PathStore(starts, actual, planned if planned_fields is not None else None,
                      action_model=action_model, ticks_per_step=ticks, max_time=max_time,
                      cancelled=cancelled)
    max_time = paths.max_time
    checkpoint(80, "Indexing tasks and events")
    warnings = []
    tasks_by_id = {}
    raw_tasks = data.get("tasks") or []
    for row in raw_tasks:
        if selected_version == "2023 LoRR":
            tid, r, c = row
            tasks_by_id[int(tid)] = {"release": 0, "stops": ((float(r), float(c)),), "assignments": [], "completions": []}
        else:
            tid, release, locations = row
            if len(locations) % 2:
                raise ValueError(f"Task {tid} must contain row/column coordinate pairs.")
            stops = tuple((float(locations[i]), float(locations[i + 1])) for i in range(0, len(locations), 2))
            tasks_by_id[int(tid)] = {"release": int(release), "stops": stops, "assignments": [], "completions": []}
    events = []
    event_id_counts = {}

    def add_event(time, agent, task_id, kind, stop=None):
        time, agent, task_id = int(time), int(agent), int(task_id)
        if not 0 <= agent < count or time < 0:
            return
        item = tasks_by_id.get(task_id)
        if item is None:
            warnings.append(f"Event references unavailable task {task_id}.")
        elif kind == "assigned":
            item["assignments"].append((time, agent))
        elif stop is not None:
            if 0 <= stop < len(item["stops"]):
                item["completions"].append((time, agent, stop))
            else:
                warnings.append(f"Task {task_id} event references unavailable stop {stop}.")
                return
        identity = f"{kind}:{time}:{agent}:{task_id}:{stop}"
        occurrence = event_id_counts.get(identity, 0)
        event_id_counts[identity] = occurrence + 1
        events.append(Event(time, agent, task_id, kind, stop, f"{identity}:{occurrence}"))

    if selected_version == "2023 LoRR":
        for agent, agent_events in enumerate((data.get("events") or [])[:count]):
            for tid, at, kind in agent_events:
                if kind == "assigned":
                    add_event(at, agent, tid, "assigned")
                elif kind == "finished":
                    add_event(at, agent, tid, "task_finished", 0)
    else:
        for agent, schedule in enumerate((data.get("actualSchedule") or [])[:count]):
            for entry in schedule.split(","):
                if not entry.strip():
                    continue
                at, tid = (int(value) for value in entry.split(":"))
                if tid >= 0:
                    add_event(at, agent, tid, "assigned")
        for at, agent, tid, next_stop in data.get("events") or []:
            tid, stop = int(tid), int(next_stop) - 1
            item = tasks_by_id.get(tid)
            kind = "task_finished" if item and stop == len(item["stops"]) - 1 else "errand_finished"
            add_event(at, agent, tid, kind, stop)
    tasks = tuple(Task(tid, item["release"], item["stops"],
                       tuple(sorted(set(item["assignments"]))), tuple(sorted(set(item["completions"]))))
                  for tid, item in sorted(tasks_by_id.items()))
    events.sort(key=lambda event: (event.time, event.id))
    conflicts = []
    for field in ("errors", "scheduleErrors"):
        for row in data.get(field) or []:
            if len(row) == 4:
                a, b, at, description = row
                tid = None
            elif len(row) == 5:
                tid, a, b, at, description = row
                tid = int(tid) if int(tid) >= 0 else None
            else:
                raise ValueError(f"{field} entries must contain four or five fields.")
            agents = tuple(sorted({int(agent) for agent in (a, b) if 0 <= int(agent) < count}))
            conflicts.append(Conflict(int(at), agents, str(description), tid))
    delays = {}
    for agent, intervals in enumerate((data.get("delayIntervals") or [])[:count]):
        if intervals:
            delays[agent] = _merge_intervals(intervals)
    metadata = {key: value for key, value in data.items()
                if key not in {"actualPaths", "plannerPaths", "start", "tasks", "events", "errors",
                               "scheduleErrors", "delayIntervals", "actualSchedule", "plannerSchedule", "plannerTimes"}}
    metadata["source"] = str(source.resolve())
    metadata["warnings"] = tuple(dict.fromkeys(warnings))
    result = PlanData(map_data, paths, tasks, tuple(events), tuple(sorted(conflicts, key=lambda c: c.time)),
                      delays, metadata, selected_version, action_model, "tick" if tick else "timestep",
                      ticks, max_time)
    checkpoint(100, "Ready")
    return result


class _LoRRConverter:
    version: str
    id: str
    label: str

    def can_read(self, data: dict) -> bool:
        return detect_version(data) == self.version

    def convert(self, data: dict, context: ConversionContext) -> PlanData:
        return _decode_lorr(data, context, self.version)


class LoRR2023Converter(_LoRRConverter):
    id, label, version = "lorr-2023", "LoRR 2023", "2023 LoRR"


class LoRR2024Converter(_LoRRConverter):
    id, label, version = "lorr-2024", "LoRR 2024", "2024 LoRR"


class LoRR2026Converter(_LoRRConverter):
    id, label, version = "lorr-2026", "LoRR 2026", "2026 LoRR"
