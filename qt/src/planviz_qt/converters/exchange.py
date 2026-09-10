"""Versioned, GUI-independent interchange for normalized PlanViz plans.

Adapters decode their source format to ``PlanData``. This module serializes
that shared contract, retaining motion runs and one-step planner predictions.
It deliberately has no dependency on the source-format registry or Qt.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from ..domain.models import Conflict, Event, MapData, PlanData, Task
from ..domain.paths import MotionSequence, PathStore


FORMAT = "planviz"
SCHEMA_VERSION = 1
_MAX_INTEGER = int(np.iinfo(np.int64).max) - 1


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object.")
    return value


def _array(value, label, length=None):
    if not isinstance(value, (list, tuple)) or (length is not None and len(value) != length):
        suffix = f" with {length} entries" if length is not None else ""
        raise ValueError(f"{label} must be an array{suffix}.")
    return value


def _integer(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= _MAX_INTEGER:
        raise ValueError(f"{label} must be an integer between {minimum} and {_MAX_INTEGER}.")
    return value


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number.")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number.")
    return number


def _text(value, label, *, empty=False):
    if not isinstance(value, str) or (not value and not empty):
        raise ValueError(f"{label} must be a {'possibly empty ' if empty else 'nonempty '}string.")
    return value


def _json_value(value, label="metadata"):
    """Copy JSON values, normalizing domain tuples and rejecting non-finite data."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} contains a non-finite number.")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item, f"{label}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError(f"{label} object keys must be strings.")
        return {key: _json_value(item, f"{label}.{key}") for key, item in value.items()}
    raise ValueError(f"{label} contains a value that is not JSON serializable.")


def _motion(value, model, label, checkpoint):
    actions, durations = [], []
    total = 0
    allowed = set("ULRDW") if model == "MAPF" else set("FRCW")
    for index, run in enumerate(_array(value, label)):
        if index % 4096 == 0:
            checkpoint()
        action, duration = _array(run, f"{label}[{index}]", 2)
        if not isinstance(action, str) or action not in allowed:
            raise ValueError(f"{label}[{index}] has unsupported {model} action {action!r}.")
        duration = _integer(duration, f"{label}[{index}].duration", 1)
        total += duration
        if total > _MAX_INTEGER:
            raise ValueError(f"{label} motion duration exceeds the supported time range.")
        if actions and actions[-1] == action:
            durations[-1] += duration
        else:
            actions.append(action)
            durations.append(duration)
    return MotionSequence(tuple(actions), tuple(durations))


def plan_to_document(plan: PlanData) -> dict:
    """Encode normalized records; memory/time scale with runs, never tick count.

    Equal actual/planned sequences use an omitted ``planned`` field. Decoding
    that field as the actual sequence preserves the prediction semantics.
    """
    agents = []
    for start, actual, planned in zip(plan.paths.starts,
                                      plan.paths.iter_motion_sequences(),
                                      plan.paths.iter_motion_sequences(planned=True)):
        item = {"start": start.tolist(), "actual": [list(run) for run in zip(actual.actions, actual.durations)]}
        if planned != actual:
            item["planned"] = [list(run) for run in zip(planned.actions, planned.durations)]
        agents.append(item)
    return {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "source_version": plan.version,
        "action_model": plan.action_model,
        "time_unit": plan.time_unit,
        "ticks_per_step": plan.ticks_per_step,
        "max_time": plan.max_time,
        "map": {"width": plan.map.width, "height": plan.map.height},
        "agents": agents,
        "tasks": [{"id": task.id, "release_time": task.release_time,
                   "stops": [list(stop) for stop in task.stops],
                   "assignments": [list(entry) for entry in task.assignments],
                   "completions": [list(entry) for entry in task.completions]}
                  for task in plan.tasks],
        "events": [{"time": event.time, "agent_id": event.agent_id,
                    "task_id": event.task_id, "kind": event.kind,
                    "stop_index": event.stop_index, "id": event.id}
                   for event in plan.events],
        "conflicts": [{"time": conflict.time, "agent_ids": list(conflict.agent_ids),
                       "description": conflict.description, "task_id": conflict.task_id}
                      for conflict in plan.conflicts],
        "delays": {str(agent): [list(interval) for interval in intervals]
                   for agent, intervals in plan.delays.items()},
        "metadata": _json_value(_object(plan.metadata, "metadata")),
    }


def dump_plan(plan: PlanData, output_path: str | Path) -> Path:
    """Write a UTF-8 canonical plan to an explicitly chosen output file."""
    destination = Path(output_path)
    document = plan_to_document(plan)
    # Validate JSON before opening the destination so a serialization failure
    # cannot truncate an existing file. Runs, not expanded states, are encoded.
    encoded = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)
    destination.write_text(encoded + "\n", encoding="utf-8")
    return destination


def decode_document(data: dict, map_data: MapData, *, team_size=None,
                    progress=None, cancelled=None) -> PlanData:
    """Validate a schema-v1 document and build the shared compressed model.

    Agent IDs are zero-based array indexes. A requested team size keeps a
    prefix of agents and filters their histories after validating the complete
    document. Task IDs without a corresponding task are accepted in diagnostic
    events/conflicts, matching LoRR input; all other references are checked.
    """
    def checkpoint(percent=None, message="Decoding PlanViz interchange"):
        if cancelled is not None and cancelled():
            raise InterruptedError("Plan loading cancelled.")
        if percent is not None and progress is not None:
            progress(int(percent), message)

    checkpoint(15, "Validating PlanViz interchange")
    _object(data, "Document")
    if data.get("format") != FORMAT:
        raise ValueError("format must be 'planviz'.")
    version = _integer(data.get("schema_version"), "schema_version", 1)
    if version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported PlanViz schema_version {version}; supported version is {SCHEMA_VERSION}.")
    model = data.get("action_model")
    if model not in ("MAPF", "MAPF_T"):
        raise ValueError("action_model must be 'MAPF' or 'MAPF_T'.")
    unit = data.get("time_unit")
    if unit not in ("tick", "timestep"):
        raise ValueError("time_unit must be 'tick' or 'timestep'.")
    ticks = _integer(data.get("ticks_per_step"), "ticks_per_step", 1)
    if unit == "timestep" and ticks != 1:
        raise ValueError("timestep inputs require ticks_per_step = 1.")
    max_time = _integer(data.get("max_time"), "max_time")
    source_version = _text(data.get("source_version", "PlanViz v1"), "source_version")
    map_info = _object(data.get("map"), "map")
    width = _integer(map_info.get("width"), "map.width", 1)
    height = _integer(map_info.get("height"), "map.height", 1)
    if (width, height) != (map_data.width, map_data.height):
        raise ValueError(f"Map dimensions {width}x{height} do not match loaded map {map_data.width}x{map_data.height}.")
    raw_agents = _array(data.get("agents"), "agents")
    total_agents = len(raw_agents)
    count = total_agents if team_size is None else min(total_agents, _integer(team_size, "team_size"))
    starts = np.empty((count, 3), dtype=np.float64)
    actual, planned = [], []
    same_plans = True
    for agent_id, raw in enumerate(raw_agents):
        if agent_id % 64 == 0:
            checkpoint(20 + 40 * agent_id // max(1, total_agents), f"Decoding agent {agent_id + 1}/{total_agents}")
        label = f"agents[{agent_id}]"
        raw = _object(raw, label)
        start = tuple(_number(value, f"{label}.start[{index}]")
                      for index, value in enumerate(_array(raw.get("start"), f"{label}.start", 3)))
        direction = start[2]
        if not (0 <= direction < 4 or (model == "MAPF" and direction == -1)):
            raise ValueError(f"{label}.start direction must be in [0, 4), or -1 for MAPF.")
        execution = _motion(raw.get("actual"), model, f"{label}.actual", checkpoint)
        prediction = (_motion(raw["planned"], model, f"{label}.planned", checkpoint)
                      if "planned" in raw else execution)
        if max(execution.length, prediction.length) > max_time:
            raise ValueError(f"{label} motion length exceeds max_time.")
        if agent_id < count:
            starts[agent_id] = start
            actual.append(execution)
            planned.append(prediction)
            same_plans = same_plans and prediction == execution

    def agent_ref(value, label):
        value = _integer(value, label)
        if value >= total_agents:
            raise ValueError(f"{label} references unavailable agent {value}.")
        return value

    tasks, tasks_by_id = [], {}
    checkpoint(65, "Decoding tasks and events")
    for index, raw in enumerate(_array(data.get("tasks", []), "tasks")):
        checkpoint()
        label = f"tasks[{index}]"
        raw = _object(raw, label)
        tid = _integer(raw.get("id"), f"{label}.id")
        if tid in tasks_by_id:
            raise ValueError(f"Duplicate task ID {tid}.")
        release = _integer(raw.get("release_time"), f"{label}.release_time")
        stops = tuple(tuple(_number(value, f"{label}.stops[{stop_index}]") for value in
                            _array(stop, f"{label}.stops[{stop_index}]", 2))
                      for stop_index, stop in enumerate(_array(raw.get("stops"), f"{label}.stops")))
        assignments, completions = [], []
        for row in _array(raw.get("assignments", []), f"{label}.assignments"):
            at, agent = _array(row, f"{label}.assignments entry", 2)
            at = _integer(at, f"{label}.assignment time")
            agent = agent_ref(agent, f"{label}.assignment agent")
            if agent < count:
                assignments.append((at, agent))
        for row in _array(raw.get("completions", []), f"{label}.completions"):
            at, agent, stop = _array(row, f"{label}.completions entry", 3)
            at = _integer(at, f"{label}.completion time")
            agent = agent_ref(agent, f"{label}.completion agent")
            stop = _integer(stop, f"{label}.completion stop")
            if stop >= len(stops):
                raise ValueError(f"{label}.completion references unavailable stop {stop}.")
            if agent < count:
                completions.append((at, agent, stop))
        task = Task(tid, release, stops, tuple(sorted(assignments, key=lambda entry: entry[0])),
                    tuple(sorted(completions, key=lambda entry: entry[0])))
        tasks.append(task)
        tasks_by_id[tid] = task
    events = []
    for index, raw in enumerate(_array(data.get("events", []), "events")):
        checkpoint()
        label = f"events[{index}]"
        raw = _object(raw, label)
        at = _integer(raw.get("time"), f"{label}.time")
        agent = agent_ref(raw.get("agent_id"), f"{label}.agent_id")
        tid = _integer(raw.get("task_id"), f"{label}.task_id")
        kind = _text(raw.get("kind"), f"{label}.kind")
        stop = raw.get("stop_index")
        if stop is not None:
            stop = _integer(stop, f"{label}.stop_index")
            task = tasks_by_id.get(tid)
            if task is not None and stop >= len(task.stops):
                raise ValueError(f"{label} references unavailable stop {stop} of task {tid}.")
        identity = _text(raw.get("id", ""), f"{label}.id", empty=True)
        if agent < count:
            events.append(Event(at, agent, tid, kind, stop, identity))
    conflicts = []
    for index, raw in enumerate(_array(data.get("conflicts", []), "conflicts")):
        checkpoint()
        label = f"conflicts[{index}]"
        raw = _object(raw, label)
        at = _integer(raw.get("time"), f"{label}.time")
        agents = tuple(agent_ref(value, f"{label}.agent_ids")
                       for value in _array(raw.get("agent_ids"), f"{label}.agent_ids"))
        if len(set(agents)) != len(agents):
            raise ValueError(f"{label}.agent_ids contains a duplicate agent.")
        description = _text(raw.get("description"), f"{label}.description", empty=True)
        tid = raw.get("task_id")
        if tid is not None:
            tid = _integer(tid, f"{label}.task_id")
        conflicts.append(Conflict(at, tuple(agent for agent in agents if agent < count), description, tid))
    delays = {}
    for raw_agent, raw_intervals in _object(data.get("delays", {}), "delays").items():
        checkpoint()
        if not isinstance(raw_agent, str) or not raw_agent.isascii() or not raw_agent.isdecimal():
            raise ValueError("delays keys must be decimal agent ID strings.")
        agent = agent_ref(int(raw_agent), "delays agent")
        if str(agent) != raw_agent:
            raise ValueError("delays keys must use canonical decimal agent IDs (for example, '0').")
        intervals = []
        for row in _array(raw_intervals, f"delays[{raw_agent}]"):
            start, end = _array(row, f"delays[{raw_agent}] interval", 2)
            start = _integer(start, f"delays[{raw_agent}] start")
            end = _integer(end, f"delays[{raw_agent}] end")
            if end < start:
                raise ValueError(f"delays[{raw_agent}] interval end precedes its start.")
            intervals.append((start, end))
        if agent < count:
            delays[agent] = tuple(intervals)
    metadata = _json_value(_object(data.get("metadata", {}), "metadata"))
    checkpoint(85, "Indexing compressed paths")
    paths = PathStore(starts, actual, None if same_plans else planned, action_model=model,
                      ticks_per_step=ticks, max_time=max_time, cancelled=cancelled)
    result = PlanData(map_data, paths, tuple(tasks), tuple(sorted(events, key=lambda event: event.time)),
                      tuple(sorted(conflicts, key=lambda conflict: conflict.time)), delays, metadata,
                      source_version, model, unit, ticks, max_time)
    checkpoint(100, "Ready")
    return result


class PlanVizConverter:
    id = "planviz"
    label = "PlanViz exchange JSON"

    def can_read(self, data: dict) -> bool:
        return data.get("format") == "planviz"

    def convert(self, data: dict, context):
        context.checkpoint(15, "Reading PlanViz exchange data")
        return decode_document(data, context.map_data, team_size=context.team_size,
                               progress=context.progress, cancelled=context.cancelled)
