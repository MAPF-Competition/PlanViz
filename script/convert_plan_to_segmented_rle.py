#!/usr/bin/env python3
"""Convert legacy PlanViz JSON paths into segmented RLE time format."""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Set, Tuple

from util import DIRECTION, state_transition, state_transition_mapf


def split_action_tokens(path_str: str, allowed_actions: Set[str]) -> List[str]:
    if not isinstance(path_str, str):
        raise ValueError(f"Path must be a string, got {type(path_str).__name__}.")

    actions: List[str] = []
    for token in [part.strip() for part in path_str.split(",") if part.strip()]:
        if len(token) == 1 and token in allowed_actions:
            actions.append(token)
            continue

        compressed = re.findall(r"([A-Za-z])(\d+)", token)
        if compressed:
            for action, repeat in compressed:
                if action in allowed_actions:
                    actions.extend([action] * int(repeat))
    return actions


def parse_start_state(raw_start: List) -> Tuple[int, int, int]:
    if not isinstance(raw_start, list) or len(raw_start) != 3:
        raise ValueError(f"Invalid start state entry: {raw_start!r}")

    row = int(raw_start[0])
    col = int(raw_start[1])
    ori_raw = raw_start[2]
    if isinstance(ori_raw, str):
        if ori_raw not in DIRECTION:
            raise ValueError(f"Unknown orientation: {ori_raw}")
        ori = DIRECTION[ori_raw]
    else:
        ori = int(ori_raw)
    return (row, col, ori)


def _scale_schedule_strings(schedules: Any, factor: int) -> Any:
    if not isinstance(schedules, list):
        return schedules

    scaled: List[Any] = []
    for schedule in schedules:
        if not isinstance(schedule, str):
            scaled.append(schedule)
            continue

        entries: List[str] = []
        for ele in [part.strip() for part in schedule.split(",") if part.strip()]:
            if ":" not in ele:
                continue
            t_str, payload = ele.split(":", 1)
            entries.append(f"{int(t_str) * factor}:{payload}")
        scaled.append(",".join(entries))
    return scaled


def _scale_error_times(errors: Any, factor: int) -> Any:
    if not isinstance(errors, list):
        return errors

    scaled: List[Any] = []
    for err in errors:
        if not isinstance(err, list):
            scaled.append(err)
            continue

        out = list(err)
        if len(out) == 4:
            out[2] = int(out[2]) * factor
        elif len(out) >= 5:
            out[3] = int(out[3]) * factor
        scaled.append(out)
    return scaled


def _scale_2024_times_to_ticks(data: Dict, factor: int) -> None:
    if "tasks" in data and isinstance(data["tasks"], list):
        scaled_tasks: List[Any] = []
        for task in data["tasks"]:
            if isinstance(task, list) and len(task) >= 2:
                out = list(task)
                out[1] = int(out[1]) * factor
                scaled_tasks.append(out)
            else:
                scaled_tasks.append(task)
        data["tasks"] = scaled_tasks

    if "events" in data and isinstance(data["events"], list):
        scaled_events: List[Any] = []
        for event in data["events"]:
            if isinstance(event, list) and len(event) >= 1:
                out = list(event)
                out[0] = int(out[0]) * factor
                scaled_events.append(out)
            else:
                scaled_events.append(event)
        data["events"] = scaled_events

    if "actualSchedule" in data:
        data["actualSchedule"] = _scale_schedule_strings(data.get("actualSchedule"), factor)
    if "plannerSchedule" in data:
        data["plannerSchedule"] = _scale_schedule_strings(data.get("plannerSchedule"), factor)
    if "errors" in data:
        data["errors"] = _scale_error_times(data.get("errors"), factor)
    if "scheduleErrors" in data:
        data["scheduleErrors"] = _scale_error_times(data.get("scheduleErrors"), factor)


def _scale_2023_times_to_ticks(data: Dict, factor: int) -> None:
    if "events" in data and isinstance(data["events"], list):
        scaled_by_agent: List[Any] = []
        for ag_events in data["events"]:
            if not isinstance(ag_events, list):
                scaled_by_agent.append(ag_events)
                continue
            scaled_events: List[Any] = []
            for event in ag_events:
                if isinstance(event, list) and len(event) >= 2:
                    out = list(event)
                    out[1] = int(out[1]) * factor
                    scaled_events.append(out)
                else:
                    scaled_events.append(event)
            scaled_by_agent.append(scaled_events)
        data["events"] = scaled_by_agent

    if "errors" in data:
        data["errors"] = _scale_error_times(data.get("errors"), factor)


def encode_tick_actions(actions: List[str], ticks_per_timestep: int) -> List[List]:
    tick_actions: List[List] = []
    if not actions:
        return tick_actions

    cur_action = actions[0]
    cur_count = 1
    for action in actions[1:]:
        if action == cur_action:
            cur_count += 1
            continue
        tick_actions.append([cur_action, cur_count * ticks_per_timestep])
        cur_action = action
        cur_count = 1
    tick_actions.append([cur_action, cur_count * ticks_per_timestep])
    return tick_actions


def _format_action_runs(tick_actions: List[List]) -> str:
    return ",".join(f"{action} {duration}" for action, duration in tick_actions)


def _build_segment_chunk(
    start_tick: int,
    row: int,
    col: int,
    direction: int,
    counter: int,
    tick_actions: List[List],
) -> str:
    actions_str = _format_action_runs(tick_actions)
    return f"[({start_tick},{row},{col},{direction},{counter}):({actions_str})]"


def build_agent_segmented_rle_path(
    start_state: Tuple[int, int, int],
    actions: List[str],
    state_trans: Callable[[Tuple[int, int, int], str], Tuple[int, int, int]],
    ticks_per_timestep: int,
    segment_horizon: int,
) -> str:
    if not actions:
        return ""

    chunks: List[str] = []
    cur_state = start_state
    counter = 0
    progress_actions = {"F", "R", "C", "U", "D", "L"}

    for step_start in range(0, len(actions), segment_horizon):
        segment_actions = actions[step_start : step_start + segment_horizon]
        start_tick = step_start * ticks_per_timestep
        tick_actions = encode_tick_actions(segment_actions, ticks_per_timestep)
        chunks.append(
            _build_segment_chunk(
                start_tick=start_tick,
                row=cur_state[0],
                col=cur_state[1],
                direction=cur_state[2],
                counter=counter,
                tick_actions=tick_actions,
            )
        )

        # Legacy input uses one whole source action per motion entry.
        # This keeps counter = 0 at segment boundaries while preserving the field.
        for action in segment_actions:
            if action in progress_actions:
                counter += ticks_per_timestep
                if counter >= ticks_per_timestep:
                    counter = 0
            cur_state = state_trans(cur_state, action)

    return "".join(chunks)


def convert_path_field(
    data: Dict,
    field_name: str,
    state_trans: Callable[[Tuple[int, int, int], str], Tuple[int, int, int]],
    allowed_actions: Set[str],
    ticks_per_timestep: int,
    segment_horizon: int,
) -> Tuple[List[str], int]:
    if field_name not in data:
        return [], 0

    team_size = int(data["teamSize"])
    starts = data.get("start", [])
    raw_paths = data[field_name]
    if not isinstance(raw_paths, list):
        raise ValueError(f"{field_name} must be a list.")
    if not isinstance(starts, list):
        raise ValueError("'start' must be a list.")
    if len(starts) < team_size:
        raise ValueError(f"'start' must have at least {team_size} entries.")

    max_steps = 0
    out_paths: List[str] = []
    for agent_id in range(team_size):
        path_str = raw_paths[agent_id] if agent_id < len(raw_paths) else ""
        actions = split_action_tokens(path_str, allowed_actions=allowed_actions)
        max_steps = max(max_steps, len(actions))
        start_state = parse_start_state(starts[agent_id])
        out_paths.append(
            build_agent_segmented_rle_path(
                start_state=start_state,
                actions=actions,
                state_trans=state_trans,
                ticks_per_timestep=ticks_per_timestep,
                segment_horizon=segment_horizon,
            )
        )

    return out_paths, max_steps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert legacy actualPaths/plannerPaths into segmented RLE strings."
    )
    parser.add_argument("input_json", type=Path, help="Input plan JSON file.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: <input>_segmented_rle.json).",
    )
    parser.add_argument(
        "--segment-horizon",
        type=int,
        default=20,
        help="Number of actions per segment (default: 20).",
    )
    parser.add_argument(
        "--keep-legacy-paths",
        action="store_true",
        help="Preserve input paths as legacyActualPaths/legacyPlannerPaths.",
    )
    return parser.parse_args()


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_segmented_rle{input_path.suffix}")


def get_time_resolution(data: Dict[str, Any]) -> int:
    if "agentMaxCounter" not in data:
        raise KeyError("Missing agentMaxCounter. Time resolution must be provided in the input JSON.")

    time_resolution = int(data["agentMaxCounter"])
    if time_resolution <= 0:
        raise ValueError("agentMaxCounter must be > 0.")
    return time_resolution


def main() -> None:
    args = parse_args()
    if args.segment_horizon <= 0:
        raise ValueError("--segment-horizon must be > 0.")

    output_path = args.output or default_output_path(args.input_json)

    with args.input_json.open("r", encoding="utf-8") as fin:
        data = json.load(fin)

    if "teamSize" not in data:
        raise KeyError("Missing teamSize.")
    if "start" not in data:
        raise KeyError("Missing start.")
    time_resolution = get_time_resolution(data)

    action_model = data.get("actionModel", "MAPF_T")
    state_trans = state_transition
    allowed_actions = {"F", "R", "C", "W", "T"}
    if action_model == "MAPF":
        state_trans = state_transition_mapf
        allowed_actions = {"U", "D", "L", "R", "W", "T"}

    legacy_actual_paths = data.get("actualPaths") if args.keep_legacy_paths else None
    legacy_planner_paths = data.get("plannerPaths") if args.keep_legacy_paths else None

    actual_paths, actual_steps = convert_path_field(
        data=data,
        field_name="actualPaths",
        state_trans=state_trans,
        allowed_actions=allowed_actions,
        ticks_per_timestep=time_resolution,
        segment_horizon=args.segment_horizon,
    )
    planner_paths, planner_steps = convert_path_field(
        data=data,
        field_name="plannerPaths",
        state_trans=state_trans,
        allowed_actions=allowed_actions,
        ticks_per_timestep=time_resolution,
        segment_horizon=args.segment_horizon,
    )

    if not actual_paths and not planner_paths:
        raise ValueError("No legacy paths found. Need actualPaths and/or plannerPaths.")

    if actual_paths:
        data["actualPaths"] = actual_paths
    if planner_paths:
        data["plannerPaths"] = planner_paths
    if args.keep_legacy_paths:
        if legacy_actual_paths is not None:
            data["legacyActualPaths"] = legacy_actual_paths
        if legacy_planner_paths is not None:
            data["legacyPlannerPaths"] = legacy_planner_paths

    # Remove alternate segmented fields so a single source of truth is kept.
    data.pop("actualPlanSegments", None)
    data.pop("plannerPlanSegments", None)

    makespan_timesteps = max(actual_steps, planner_steps)
    if "makespan" in data:
        makespan_timesteps = max(makespan_timesteps, int(data["makespan"]))
    makespan_ticks = makespan_timesteps * time_resolution

    version = str(data.get("version", ""))
    if version == "2024 LoRR":
        _scale_2024_times_to_ticks(data, time_resolution)
    else:
        _scale_2023_times_to_ticks(data, time_resolution)

    data["makespanTimesteps"] = makespan_timesteps
    data["makespanTicks"] = makespan_ticks
    data["makespan"] = makespan_ticks
    data["agentMaxCounter"] = time_resolution

    with output_path.open("w", encoding="utf-8") as fout:
        json.dump(data, fout, indent=4)

    print(f"Saved converted plan to: {output_path}")
    print(
        f"teamSize={data['teamSize']} makespan={data['makespan']} "
        f"(from sourceActions={data['makespanTimesteps']})"
    )
    print(f"hasActualPaths={bool(actual_paths)} hasPlannerPaths={bool(planner_paths)}")


if __name__ == "__main__":
    main()
