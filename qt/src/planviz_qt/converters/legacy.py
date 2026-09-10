"""Standalone tracker CSV and coordinate-text conversion helpers.

Run ``planviz-convert --help`` for the CLI subcommands. Legacy conversion helpers
return 2023 LoRR dictionaries. Files are written only when an explicit output
path is passed; existing Tk tools and their formats are not imported.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import re


from .errors import ConversionError


def _integer(value, label, *, minimum=0):
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ConversionError(f"{label} must be an integer, got {value!r}.") from exc
    if result < minimum:
        raise ConversionError(f"{label} must be at least {minimum}.")
    return result


def _assemble(starts, goals, motions, *, cost=None, errors=None):
    if not (len(starts) == len(goals) == len(motions)):
        raise ConversionError("Start, goal, and path agent counts must match.")
    lengths = [len(path) for path in motions]
    makespan = max(lengths, default=0)
    padded = [",".join(path + "W" * (makespan - len(path))) for path in motions]
    errors = errors or []
    return {"version": "2023 LoRR", "actionModel": "MAPF", "AllValid": "No" if errors else "Yes",
            "teamSize": len(starts), "start": [[r, c, "N/A"] for r, c in starts],
            "numTaskFinished": len(starts), "sumOfCost": sum(lengths) if cost is None else cost,
            "makespan": makespan, "actualPaths": padded, "plannerPaths": list(padded),
            "plannerTimes": [], "errors": errors,
            "events": [[[agent, 0, "assigned"], [agent, length, "finished"]]
                       for agent, length in enumerate(lengths)],
            "tasks": [[agent, r, c] for agent, (r, c) in enumerate(goals)]}


def _output_path(output):
    path = Path(output)
    return path if path.suffix.lower() == ".json" else path.with_name(path.name + ".json")


def _write(output, data):
    path = _output_path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
    return path


def _conflicts(path, team_size):
    result = []
    descriptions = {"V": "vertex conflict", "E": "edge conflict", "T": "target conflict"}
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.reader(stream))
    for index, row in enumerate(rows):
        if not row or all(not item.strip() for item in row):
            continue
        try:
            a, b = int(row[0]), int(row[1])
        except (ValueError, IndexError):
            if index == 0:
                continue  # The original exporter includes a header.
            raise ConversionError(f"Conflict row {index + 1}: invalid agent IDs.") from None
        if len(row) < 4 or not (0 <= a < team_size and 0 <= b < team_size):
            raise ConversionError(f"Conflict row {index + 1}: invalid fields or agent ID.")
        at = _integer(row[-2], f"Conflict row {index + 1} time")
        kind = row[-1].strip().upper()
        if kind not in descriptions:
            raise ConversionError(f"Conflict row {index + 1}: unsupported type {kind!r}.")
        result.append([a, b, at, descriptions[kind]])
    return result


def convert_paths(path_file, output_file=None, conflict_file=None) -> dict:
    """Convert ``Agent 0: (row,col)->...`` paths; reject noncardinal moves."""
    starts, goals, motions = [], [], []
    with Path(path_file).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            match = re.fullmatch(r"\s*Agent\s*(\d+)\s*:\s*(.*?)\s*", line)
            if not match:
                raise ConversionError(f"Path line {line_number}: expected 'Agent N: (row,col)->...'.")
            agent = int(match.group(1))
            if agent != len(starts):
                raise ConversionError(f"Path line {line_number}: expected agent {len(starts)}, got {agent}.")
            payload = match.group(2)
            if payload.endswith("->"):
                payload = payload[:-2]
            positions = []
            for token in payload.split("->"):
                loc = re.fullmatch(r"\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)\s*", token)
                if not loc:
                    raise ConversionError(f"Agent {agent}: invalid coordinate {token!r}.")
                positions.append((int(loc.group(1)), int(loc.group(2))))
            if not positions:
                raise ConversionError(f"Agent {agent}: an initial position is required.")
            actions = []
            # The viewer's legacy MAPF encoding uses U for increasing row.
            # Coordinate input is physical row/column, so down must become U.
            mapping = {(0, 0): "W", (0, 1): "R", (0, -1): "L", (1, 0): "U", (-1, 0): "D"}
            for step, (previous, following) in enumerate(zip(positions, positions[1:])):
                delta = (following[0] - previous[0], following[1] - previous[1])
                if delta not in mapping:
                    raise ConversionError(f"Agent {agent}, move {step}: noncardinal move {previous} -> {following}.")
                actions.append(mapping[delta])
            starts.append(positions[0])
            goals.append(positions[-1])
            motions.append("".join(actions))
    if not starts:
        raise ConversionError("The path file contains no agents.")
    errors = _conflicts(conflict_file, len(starts)) if conflict_file else []
    result = _assemble(starts, goals, motions, errors=errors)
    if output_file is not None:
        _write(output_file, result)
    return result


def _scenario(path, count, expected_map=None):
    starts, goals = [], []
    with Path(path).open("r", encoding="utf-8") as stream:
        header = stream.readline().strip()
        if not header.lower().startswith("version"):
            raise ConversionError(f"Scenario {path}: expected a version header.")
        for line_number, line in enumerate(stream, 2):
            if not line.strip():
                continue
            fields = line.split()
            if len(fields) < 9:
                raise ConversionError(f"Scenario {path}, line {line_number}: expected nine fields.")
            width = _integer(fields[2], "Scenario width", minimum=1)
            height = _integer(fields[3], "Scenario height", minimum=1)
            sx, sy, gx, gy = (_integer(value, f"Scenario line {line_number} coordinate") for value in fields[4:8])
            if not (sx < width and gx < width and sy < height and gy < height):
                raise ConversionError(f"Scenario {path}, line {line_number}: coordinate outside declared map.")
            if expected_map is not None and Path(fields[1]).stem != Path(expected_map).stem:
                raise ConversionError(f"Scenario {path}: map {fields[1]!r} does not match {expected_map!r}.")
            starts.append((sy, sx))
            goals.append((gy, gx))
            if len(starts) == count:
                break
    if len(starts) < count:
        raise ConversionError(f"Scenario contains {len(starts)} agent records; plan requires {count}.")
    return starts, goals


def _tracker_row(row, scenario_path, path_column, row_index, expected_map=None):
    count = _integer(row.get("agents"), f"CSV row {row_index} agents", minimum=1)
    if path_column not in row or row[path_column] is None:
        raise ConversionError(f"CSV row {row_index}: missing {path_column!r} column.")
    raw_paths = row[path_column].replace("\r\n", "\n").split("\n")
    if len(raw_paths) == count + 1 and not raw_paths[-1].strip():
        raw_paths.pop()
    if len(raw_paths) != count:
        raise ConversionError(f"CSV row {row_index}: {count} agents but {len(raw_paths)} paths.")
    motions = []
    mapping = str.maketrans({"U": "D", "D": "U"})
    for agent, text in enumerate(raw_paths):
        text = text.strip().upper()
        if any(action not in "ULRDWT" for action in text):
            raise ConversionError(f"CSV row {row_index}, agent {agent}: unsupported path action.")
        motions.append(text.translate(mapping))
    starts, goals = _scenario(scenario_path, count, expected_map)
    cost = row.get("solution_cost")
    cost = _integer(cost, f"CSV row {row_index} solution_cost") if cost not in (None, "") else None
    return _assemble(starts, goals, motions, cost=cost)


def convert_tracker(plan_file, scenario, output_file=None, *, multi=False) -> list[dict]:
    """Convert single ``path`` or bulk ``solution_plan`` CSV records.

    In bulk mode scenario is a folder containing
    ``<map_name>-<scen_type>-<type_id>.scen``. Output receives numeric row suffixes.
    All rows are validated before any output files are written.
    """
    with Path(plan_file).open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ConversionError("The tracker CSV contains no data rows.")
    converted = []
    for index, row in enumerate(rows if multi else rows[:1]):
        expected_map = None
        if multi:
            components = []
            for key in ("map_name", "scen_type"):
                value = row.get(key, "")
                if not value or value in (".", "..") or "/" in value or "\\" in value:
                    raise ConversionError(f"CSV row {index}: unsafe or missing {key}.")
                components.append(value)
            type_id = _integer(row.get("type_id"), f"CSV row {index} type_id")
            scenario_path = Path(scenario) / f"{components[0]}-{components[1]}-{type_id}.scen"
            expected_map = components[0]
        else:
            scenario_path = Path(scenario)
        converted.append(_tracker_row(row, scenario_path, "solution_plan" if multi else "path", index, expected_map))
    if output_file is not None:
        target = _output_path(output_file)
        for index, result in enumerate(converted):
            output = target.with_name(f"{target.stem}_{index}.json") if multi else target
            _write(output, result)
    return converted


