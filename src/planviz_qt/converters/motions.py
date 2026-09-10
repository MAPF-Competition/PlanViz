"""Motion text adapters that retain run-length compression."""

from __future__ import annotations

import re

from ..domain.paths import MotionSequence

_CHUNK = re.compile(r"\[\(([^)]*)\):\(([^)]*)\)\]")


def parse_motion_sequence(text: str, *, tick: bool = False,
                          action_model: str = "MAPF_T", label: str = "path") -> MotionSequence:
    if not isinstance(text, str):
        raise ValueError(f"{label} must be a string.")
    allowed = set("ULRDWT") if action_model == "MAPF" else set("FRCWT")
    actions, durations = [], []

    def append(action, duration):
        if action not in allowed:
            raise ValueError(f"{label}: unsupported {action_model} action {action!r}.")
        if duration < 0:
            raise ValueError(f"{label}: run duration must not be negative.")
        if duration == 0:
            return
        action = "W" if action == "T" else action
        if actions and actions[-1] == action:
            durations[-1] += duration
        else:
            actions.append(action)
            durations.append(duration)

    if not text.strip():
        return MotionSequence((), ())
    if tick or text.lstrip().startswith("[("):
        cursor, total, chunks = 0, 0, 0
        for match in _CHUNK.finditer(text):
            if text[cursor:match.start()].strip():
                raise ValueError(f"{label}: invalid text between RLE chunks.")
            fields = [s.strip() for s in match.group(1).split(",")]
            if len(fields) != 5:
                raise ValueError(f"{label}: RLE state needs startTick,row,col,direction,counter.")
            try:
                start_tick = int(fields[0])
                for value in fields[1:]:
                    float(value)
            except ValueError as exc:
                raise ValueError(f"{label}: invalid RLE state field.") from exc
            if start_tick != total:
                raise ValueError(f"{label}: expected contiguous chunk at tick {total}, got {start_tick}.")
            for token in match.group(2).split(","):
                if not token.strip():
                    continue
                parts = token.split()
                if len(parts) != 2:
                    raise ValueError(f"{label}: expected '<action> <duration>', got {token!r}.")
                try:
                    duration = int(parts[1])
                except ValueError as exc:
                    raise ValueError(f"{label}: invalid run duration {parts[1]!r}.") from exc
                append(parts[0], duration)
                total += duration
            cursor, chunks = match.end(), chunks + 1
        if not chunks or text[cursor:].strip():
            raise ValueError(f"{label}: invalid segmented RLE path.")
    else:
        # Legacy files use comma-separated actions; compact text is accepted
        # for converter output as well. Never allocate a tick history.
        for action in text:
            if action == "," or action.isspace():
                continue
            append(action, 1)
    return MotionSequence(tuple(actions), tuple(durations))
