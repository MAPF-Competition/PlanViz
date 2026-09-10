"""Read existing PlanViz overlay formats into toolkit-independent layers.

Legacy formats: heatmap plan JSON, encoded highway edge text, per-agent
heuristic CSV rows, and search-tree CSV with a ``loc`` column. JSON matrices
and explicit highway edge JSON are also accepted. No GUI objects are created.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import io
import json
from pathlib import Path
import re
from typing import Callable

import numpy as np

from ..domain.models import MapData


@dataclass(frozen=True)
class Overlay:
    name: str
    kind: str
    values: np.ndarray | None = None
    segments: tuple[tuple[float, float, float, float], ...] = ()
    source: str = ""
    colormap: str = "Reds"


_KINDS = {"hm": "heatmap", "heat_map": "heatmap", "hw": "highway",
          "heu": "heuristic", "searchTree": "search_tree", "search-tree": "search_tree"}


def load_overlay(path: str | Path, kind: str, map_data: MapData, *,
                 agent_id: int = 104,
                 cancelled: Callable[[], bool] | None = None) -> Overlay:
    """Load a layer; locations and directed segments use row/column coordinates.

    The heuristic's default agent 104 preserves the old ``--heu`` behavior;
    callers may select another agent explicitly. Heatmap counts omit terminal
    states and trailing W actions, as in the existing viewer. For tick plans,
    sampled fractional positions are assigned to the nearest map cell.
    """
    _check_cancelled(cancelled)
    path = Path(path).expanduser()
    kind = _KINDS.get(kind, kind)
    if kind not in {"heatmap", "highway", "heuristic", "search_tree"}:
        raise ValueError(f"Unknown overlay kind: {kind!r}")
    text = path.read_text(encoding="utf-8-sig")
    _check_cancelled(cancelled)
    stripped = text.lstrip()
    data = json.loads(text) if stripped.startswith(("{", "[")) else None
    _check_cancelled(cancelled)
    values = None
    segments = ()
    if kind == "highway":
        segments = _highway(data, text, map_data, cancelled)
    elif kind == "heatmap":
        if isinstance(data, dict) and "actualPaths" in data:
            values = _heatmap_from_plan(data, map_data, cancelled)
        elif data is None and stripped.startswith("Agent"):
            values = _heatmap_from_paths(text, map_data, cancelled)
        else:
            values = _matrix(data if data is not None else _numeric_rows(text, cancelled), map_data)
    elif kind == "heuristic":
        if data is not None:
            if isinstance(data, dict) and "agents" in data:
                records = data["agents"]
                key = str(agent_id) if isinstance(records, dict) else agent_id
                try:
                    data = records[key]
                except (KeyError, IndexError) as error:
                    raise ValueError(f"Heuristic has no agent {agent_id}") from error
            values = _matrix(data, map_data, allow_unreachable=True)
        else:
            rows = _numeric_rows(text, cancelled)
            cell_count = map_data.height * map_data.width
            if rows and all(len(row) == cell_count + 1 for row in rows):
                selected = [row[1:] for row in rows if row[0] == agent_id]
                if len(selected) != 1:
                    raise ValueError(f"Expected one heuristic row for agent {agent_id}, got {len(selected)}")
                rows = selected[0]
            values = _matrix(rows, map_data, allow_unreachable=True)
    elif kind == "search_tree":
        values = _search_tree(data, text, map_data, cancelled)
    _check_cancelled(cancelled)
    if values is not None:
        values = np.asarray(values, dtype=np.float64)
        values.setflags(write=False)
    colormap = {"heatmap": "Reds", "heuristic": "Greys", "search_tree": "Blues",
                "highway": "Reds"}[kind]
    return Overlay(path.stem, kind, values, segments, str(path.resolve()), colormap)


def _check_cancelled(cancelled) -> None:
    if cancelled is not None and cancelled():
        raise InterruptedError("Overlay loading cancelled")


def _numeric_rows(text: str, cancelled=None) -> list[list[float]]:
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if number % 256 == 1:
            _check_cancelled(cancelled)
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append([float(value) for value in re.split(r"[,\s]+", line) if value])
        except ValueError as error:
            raise ValueError(f"Expected numeric overlay values on line {number}") from error
    return rows


def _matrix(data, map_data: MapData, *, allow_unreachable: bool = False) -> np.ndarray:
    if isinstance(data, dict):
        for key in ("values", "heatmap", "heuristic", "grid"):
            if key in data:
                data = data[key]
                break
        else:
            raise ValueError("A raster overlay JSON object needs a values or grid array")
    try:
        values = np.asarray(data, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError("Overlay values must form a rectangular numeric array") from error
    expected = (map_data.height, map_data.width)
    if values.shape in {(map_data.height * map_data.width,),
                        (1, map_data.height * map_data.width)}:
        values = values.reshape(expected)
    if values.shape != expected:
        raise ValueError(f"Overlay shape {values.shape} does not match map shape {expected}")
    values = values.copy()
    if allow_unreachable:
        values[(~np.isfinite(values)) | (values == 2**31 - 1) | (values >= 1e308)] = np.nan
    elif not np.all(np.isfinite(values)):
        raise ValueError("Overlay values must be finite")
    return values


def _location(value, map_data: MapData) -> tuple[float, float]:
    if isinstance(value, (int, float, np.number)):
        loc = int(value)
        if loc != value or not 0 <= loc < map_data.width * map_data.height:
            raise ValueError(f"Cell index {value!r} is outside the map")
        return float(loc // map_data.width), float(loc % map_data.width)
    if not isinstance(value, (list, tuple, np.ndarray)) or len(value) != 2:
        raise ValueError(f"Expected a cell index or row/column pair, got {value!r}")
    row, col = map(float, value)
    if not (np.isfinite(row) and np.isfinite(col)
            and 0 <= row < map_data.height and 0 <= col < map_data.width):
        raise ValueError(f"Cell ({row}, {col}) is outside the map")
    return row, col


def _highway(data, text: str, map_data: MapData, cancelled=None) -> tuple:
    cell_count = map_data.width * map_data.height
    if data is None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise ValueError("Highway file is empty")
        try:
            count = int(lines[0])
            encoded = [int(line) for line in lines[1:]]
        except ValueError as error:
            raise ValueError("Legacy highway needs an edge count followed by encoded integer edges") from error
        if count != len(encoded):
            raise ValueError(f"Highway declares {count} edges but contains {len(encoded)}")
        edges = [((edge // cell_count) - 1, edge % cell_count) for edge in encoded]
    else:
        edges = data.get("edges", data.get("highway")) if isinstance(data, dict) else data
        if not isinstance(edges, list):
            raise ValueError("Highway JSON needs an edges list")
    result = []
    for number, edge in enumerate(edges):
        if number % 1024 == 0:
            _check_cancelled(cancelled)
        if isinstance(edge, dict):
            try:
                start, end = edge["from"], edge["to"]
            except KeyError as error:
                raise ValueError("Highway edges need from and to locations") from error
        elif isinstance(edge, (list, tuple)) and len(edge) == 4:
            start, end = edge[:2], edge[2:]
        elif isinstance(edge, (list, tuple)) and len(edge) == 2:
            start, end = edge
        else:
            raise ValueError(f"Invalid highway edge: {edge!r}")
        row1, col1 = _location(start, map_data)
        row2, col2 = _location(end, map_data)
        if not np.isclose(abs(row2 - row1) + abs(col2 - col1), 1.0):
            raise ValueError("Highway edges must connect adjacent four-neighbour cells")
        result.append((row1, col1, row2, col2))
    return tuple(result)


def _add_positions(values: np.ndarray, positions: np.ndarray, map_data: MapData) -> None:
    if not len(positions):
        return
    positions = np.asarray(positions, dtype=float)
    if not np.all(np.isfinite(positions[:, :2])):
        raise ValueError("Heatmap path contains nonfinite coordinates")
    cells = np.floor(positions[:, :2] + 0.5).astype(np.int64)
    valid = ((cells[:, 0] >= 0) & (cells[:, 0] < map_data.height)
             & (cells[:, 1] >= 0) & (cells[:, 1] < map_data.width))
    if not np.all(valid):
        raise ValueError(f"Heatmap path leaves the map at cell {tuple(cells[~valid][0])}")
    np.add.at(values, (cells[:, 0], cells[:, 1]), 1)


def _heatmap_from_plan(data: dict, map_data: MapData, cancelled=None) -> np.ndarray:
    from ..domain.paths import PathStore
    from .motions import parse_motion_sequence

    starts, paths = data.get("start"), data.get("actualPaths")
    if not isinstance(starts, list) or not isinstance(paths, list) or len(starts) != len(paths):
        raise ValueError("Heatmap plan needs equally sized start and actualPaths lists")
    action_model = data.get("actionModel", "MAPF_T")
    tick = data.get("version") == "2026 LoRR" or data.get("timeUnit") == "tick"
    ticks = int(data.get("agentMaxCounter", 10)) if tick else 1
    orientations = {"E": 0, "N": 1, "W": 2, "S": 3, "N/A": -1}
    values = np.zeros((map_data.height, map_data.width), dtype=float)
    for agent, (start, text) in enumerate(zip(starts, paths)):
        _check_cancelled(cancelled)
        sequence = parse_motion_sequence(text, tick=tick, action_model=action_model,
                                         label=f"heatmap actualPaths[{agent}]")
        # The shared path decoder merges stationary T and W actions. Preserve
        # original heatmap semantics: task service T samples count, trailing
        # literal W samples do not. Inspect the original text before trimming.
        length = sequence.length - _trailing_wait_ticks(text)
        if not length:
            continue
        if not isinstance(start, (list, tuple)) or len(start) < 3:
            raise ValueError(f"Invalid start state for heatmap agent {agent}")
        try:
            orientation = orientations[start[2]] if isinstance(start[2], str) else float(start[2])
        except (KeyError, ValueError, TypeError) as error:
            raise ValueError(f"Invalid orientation for heatmap agent {agent}") from error
        store = PathStore(np.asarray([[float(start[0]), float(start[1]), orientation]]),
                          [sequence], action_model=action_model, ticks_per_step=ticks,
                          cancelled=cancelled)
        # Preserve every occupied sample with bounded temporary memory. This is
        # preprocessing work, intended for the application's loader worker.
        for begin in range(0, length, 65_536):
            _check_cancelled(cancelled)
            end = min(length - 1, begin + 65_535)
            positions = store.trajectory(0, begin, end, max_points=65_536)
            _add_positions(values, positions, map_data)
    return values


def _trailing_wait_ticks(text: str) -> int:
    if text.lstrip().startswith("[("):
        trailing = 0
        for chunk in re.finditer(r"\[\([^)]*\):\(([^)]*)\)\]", text):
            for token in chunk.group(1).split(","):
                if not token.strip():
                    continue
                action, count = token.split()
                duration = int(count)
                if duration:
                    trailing = trailing + duration if action == "W" else 0
        return trailing
    trailing = 0
    for action in reversed(text):
        if action == "," or action.isspace():
            continue
        if action != "W":
            break
        trailing += 1
    return trailing


def _heatmap_from_paths(text: str, map_data: MapData, cancelled=None) -> np.ndarray:
    values = np.zeros((map_data.height, map_data.width), dtype=float)
    for line_number, line in enumerate(text.splitlines(), 1):
        _check_cancelled(cancelled)
        if not line.strip():
            continue
        if re.match(r"\s*Agent\s+\d+\s*:", line) is None:
            raise ValueError(f"Invalid path-transfer line {line_number}")
        points = [(float(row), float(col)) for row, col in
                  re.findall(r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)", line)]
        if not points:
            raise ValueError(f"No path coordinates on line {line_number}")
        while len(points) > 1 and points[-1] == points[-2]:
            points.pop()
        _add_positions(values, np.asarray(points[:-1]), map_data)
    return values


def _search_tree(data, text: str, map_data: MapData, cancelled=None) -> np.ndarray:
    if isinstance(data, dict) and any(key in data for key in ("values", "grid")):
        return _matrix(data, map_data)
    if data is None:
        reader = csv.DictReader(io.StringIO(text))
        fields = set(reader.fieldnames or ())
        if "loc" not in fields and not {"row", "col"} <= fields:
            raise ValueError("Search-tree CSV needs a loc column (or row and col)")
        records = list(reader)
    elif isinstance(data, dict):
        records = data.get("nodes", data.get("search_tree"))
    else:
        records = data
    if not isinstance(records, list):
        raise ValueError("Search tree needs CSV rows or a JSON nodes list")
    values = np.zeros((map_data.height, map_data.width), dtype=float)
    for number, record in enumerate(records):
        if number % 1024 == 0:
            _check_cancelled(cancelled)
        if not isinstance(record, dict):
            raise ValueError("Search-tree nodes must have a loc field")
        if "loc" in record:
            try:
                location = _location(float(record["loc"]), map_data)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid search-tree loc: {record['loc']!r}") from error
        elif "row" in record and "col" in record:
            location = _location((record["row"], record["col"]), map_data)
        else:
            raise ValueError("Search-tree CSV needs a loc column (or row and col)")
        row, col = location
        if row != int(row) or col != int(col):
            raise ValueError("Search-tree locations must be integer cells")
        values[int(row), int(col)] += 1
    return values
