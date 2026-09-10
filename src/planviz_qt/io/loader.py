"""Read input once, select a converter, and return GUI-independent plan data."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Callable
import numpy as np

from ..domain.models import MapData, PlanData
from ..domain.validation import record_warnings
from ..converters.errors import LoadCancelled, PlanLoadError
from ..converters.base import ConversionContext


def load_map(map_path: str | Path) -> MapData:
    source = Path(map_path)
    try:
        with source.open("r", encoding="utf-8") as stream:
            if stream.readline().strip().lower() != "type octile":
                raise ValueError("Expected a 'type octile' header line.")
            height_line, width_line = stream.readline().split(), stream.readline().split()
            if len(height_line) != 2 or height_line[0].lower() != "height":
                raise ValueError("Expected a 'height <integer>' header line.")
            if len(width_line) != 2 or width_line[0].lower() != "width":
                raise ValueError("Expected a 'width <integer>' header line.")
            header_height, width = int(height_line[1]), int(width_line[1])
            if stream.readline().strip().lower() != "map":
                raise ValueError("Expected a 'map' header line.")
            rows = [line.strip() for line in stream if line.strip()]
        if width <= 0 or header_height <= 0:
            raise ValueError("Map width and height must be positive.")
        if len(rows) != header_height:
            raise ValueError(f"Map declares height {header_height}, but contains {len(rows)} rows.")
        if any(len(row) != width for row in rows):
            raise ValueError("Map dimensions or row widths are invalid.")
        lookup = np.full(256, 255, dtype=np.uint8)
        for char, value in (("@", 0), ("T", 0), (".", 1), ("S", 1), ("E", 2)):
            lookup[ord(char)] = value
        grid = lookup[np.frombuffer("".join(rows).encode("ascii"), dtype=np.uint8)].reshape(len(rows), width)
        if np.any(grid == 255):
            raise ValueError("Map contains unsupported terrain characters.")
        grid.flags.writeable = False
        return MapData(grid, str(source.resolve()), source.stem)
    except (OSError, ValueError, IndexError, UnicodeError) as exc:
        raise PlanLoadError(f"Cannot load map {source}: {exc}") from exc

def load_plan(map_path: str | Path, plan_path: str | Path, *, version: str | None = None,
              team_size: int | None = None, input_format: str = "auto", registry=None,
              progress: Callable | None = None,
              cancelled: Callable[[], bool] | None = None) -> PlanData:
    """Load JSON once and route through a registered source converter.

    Existing LoRR callers keep the same API. New formats implement InputConverter
    and register with ConverterRegistry; playback and rendering need no changes.
    JSON decoding itself cannot be interrupted; conversion checkpoints can.
    """
    from ..converters.registry import default_registry
    from ..converters.lorr import normalize_version, VERSIONS

    source = Path(plan_path)
    def checkpoint(percent, message):
        if cancelled is not None and cancelled():
            raise LoadCancelled("Plan loading cancelled.")
        if progress is not None:
            progress(percent, message)

    checkpoint(0, "Reading map")
    map_data = load_map(map_path)
    checkpoint(5, "Reading plan JSON")
    try:
        with source.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        checkpoint(12, "Selecting input converter")
        if not isinstance(data, dict):
            raise ValueError("The JSON root must be an object.")
        if team_size is not None and (isinstance(team_size, bool) or not isinstance(team_size, int) or team_size < 0):
            raise ValueError("team_size must be a nonnegative integer.")
        if version is not None:
            selected_version = normalize_version(version)
            if selected_version not in VERSIONS:
                raise ValueError(f"Unsupported version {version!r}.")
            requested = "lorr-" + selected_version[:4]
            if input_format not in ("auto", requested):
                raise ValueError("--version and --format select different converters.")
            input_format = requested
        converters = default_registry() if registry is None else registry
        converter = converters.resolve(data, input_format)
        context = ConversionContext(map_data, source, team_size,
                                    lambda percent, message: checkpoint(12 + 83*percent//100, message), cancelled)
        result = converter.convert(data, context)
        checkpoint(99, "Checking record consistency")
        existing = result.metadata.get("warnings") or ()
        if not isinstance(existing, (list, tuple)):
            existing = (existing,)
        warnings = tuple(dict.fromkeys((*map(str, existing), *record_warnings(result, cancelled=cancelled))))
        if warnings:
            result = replace(result, metadata={**result.metadata, "warnings": warnings})
        checkpoint(100, "Ready")
        return result
    except LoadCancelled:
        raise
    except InterruptedError as exc:
        raise LoadCancelled(str(exc)) from exc
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
        raise PlanLoadError(f"Cannot load plan {source}: {exc}") from exc
