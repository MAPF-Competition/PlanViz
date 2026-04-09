# -*- coding: UTF-8 -*-
""" Utility functions
"""

import sys
import math
from enum import Enum
from typing import List, Tuple, Dict
from numba import njit, prange

TASK_COLORS: Dict[int, str] = {
    "unassigned": "#eeeaa2",
    "newlyassigned": "yellowgreen",
    "assigned": "orange",
    "finished": "#C0C0C0"
}

AGENT_COLORS: Dict[str, str] = {
    "newlyassigned": "yellowgreen",
    "assigned": "deepskyblue",
    "errand_finished": "limegreen",
    "delayed": "yellow",
    "collide": "red"
}


class AgentStatus(str, Enum):
    NORMAL = "normal"
    DELAYED = "delayed"
    ERRAND_FINISHED = "errand_finished"

    @property
    def color_key(self) -> str:
        if self == AgentStatus.NORMAL:
            return "assigned"
        return self.value

DIRECTION: Dict[str,int] = {"E":0, "N":1, "W":2, "S":3, "N/A":-1}

OBSTACLES: List[str] = ['@', 'T']

MAP_CONFIG: Dict[str,Dict] = {
    "Paris_1_256": {"pixel_per_move": 2, "moves": 2, "delay": 0.06},
    "brc202d": {"pixel_per_move": 2, "moves": 2, "delay": 0.06},
    "random-32-32-20": {"pixel_per_move": 5, "moves": 5, "delay": 0.06},
    "warehouse_large": {"pixel_per_move": 2, "moves": 2, "delay": 0.06},
    "warehouse_small": {"pixel_per_move": 5, "moves": 5, "delay": 0.06},
    "sortation_large": {"pixel_per_move": 2, "moves": 2, "delay": 0.06}
}

DIR_DIAMETER:float = 0.1
DIR_OFFSET:float = 0.05
INT_MAX:int = 2**31 - 1
DBL_MAX:int = 1.79769e+308
TEXT_SIZE:int = 12

MOTION_CODE = {"F": 0, "R": 1, "C": 2, "W": 3, "T": 3}
MOTION_CODE_MAPF = {"U": 0, "L": 1, "R": 2, "D": 3, "W": 4, "T": 4}


def get_map_name(in_file:str) -> str:
    """Get the map name from the file name

    Args:
        in_file (str): the path of the map file

    Returns:
        str: the name of the map
    """
    return in_file.split("/")[-1].split(".")[0]


def get_angle(glob_dir:int):
    out_angle = 0
    if glob_dir == 0:  # East
        out_angle = 0
    elif glob_dir == 1:  # North
        out_angle = math.pi / 2.
    elif glob_dir == 2:  # West
        out_angle = math.pi
    elif glob_dir == 3:  # South
        out_angle = -1 * math.pi / 2.
    else:
        # Support fractional orientations (e.g. tick-based intermediate states)
        out_angle = float(glob_dir) * math.pi / 2.
    return out_angle


def get_dir_loc(_loc_:Tuple[int]):
    dir_loc = [0.0, 0.0, 0.0, 0.0]
    if _loc_[2] == 0:  # East
        dir_loc[1] = _loc_[0] + 0.5 - DIR_DIAMETER
        dir_loc[0] = _loc_[1] + 1 - DIR_OFFSET - DIR_DIAMETER*2
        dir_loc[3] = _loc_[0] + 0.5 + DIR_DIAMETER
        dir_loc[2] = _loc_[1] + 1 - DIR_OFFSET
    elif _loc_[2] == 3:  # South
        dir_loc[1] = _loc_[0] + 1 - DIR_OFFSET - DIR_DIAMETER*2
        dir_loc[0] = _loc_[1] + 0.5 - DIR_DIAMETER
        dir_loc[3] = _loc_[0] + 1 - DIR_OFFSET
        dir_loc[2] = _loc_[1] + 0.5 + DIR_DIAMETER
    elif _loc_[2] == 2:  # West
        dir_loc[1] = _loc_[0] + 0.5 - DIR_DIAMETER
        dir_loc[0] = _loc_[1] + DIR_OFFSET
        dir_loc[3] = _loc_[0] + 0.5 + DIR_DIAMETER
        dir_loc[2] = _loc_[1] + DIR_OFFSET + DIR_DIAMETER*2
    elif _loc_[2] == 1:  # North
        dir_loc[1] = _loc_[0] + DIR_OFFSET
        dir_loc[0] = _loc_[1] + 0.5 - DIR_DIAMETER
        dir_loc[3] = _loc_[0] + DIR_OFFSET + DIR_DIAMETER*2
        dir_loc[2] = _loc_[1] + 0.5 + DIR_DIAMETER
    else:
        # Support fractional orientations (e.g. tick-based intermediate states)
        ang = get_angle(_loc_[2])
        offset = 0.5 - DIR_OFFSET - DIR_DIAMETER
        center_col = _loc_[1] + 0.5 + offset * math.cos(ang)
        center_row = _loc_[0] + 0.5 - offset * math.sin(ang)
        dir_loc[0] = center_col - DIR_DIAMETER
        dir_loc[1] = center_row - DIR_DIAMETER
        dir_loc[2] = center_col + DIR_DIAMETER
        dir_loc[3] = center_row + DIR_DIAMETER
    return dir_loc


def get_rotation(cur_dir:int, next_dir:int):
    if cur_dir == next_dir:
        return 0
    if cur_dir == 0:
        if next_dir == 1:
            return 1  # Counter-clockwise 90 degrees
        if next_dir == 3:
            return -1  # Clockwise 90 degrees
    elif cur_dir == 1:
        if next_dir == 2:
            return 1
        if next_dir == 0:
            return -1
    elif cur_dir == 2:
        if next_dir == 3:
            return 1
        if next_dir == 1:
            return -1
    elif cur_dir == 3:
        if next_dir == 0:
            return 1
        if next_dir == 2:
            return -1

    # Support fractional orientations (e.g. tick-based intermediate states)
    cur_f = float(cur_dir)
    nxt_f = float(next_dir)
    delta = (nxt_f - cur_f) % 4.0
    if delta > 2.0:
        delta -= 4.0
    return delta


def state_transition(cur_state:Tuple[int,int,int], motion:str) -> Tuple[int,int,int]:
    if motion == "F":  # Forward
        if cur_state[-1] == 0:  # Right
            return (cur_state[0], cur_state[1]+1, cur_state[2])
        if cur_state[-1] == 1:  # Up
            return (cur_state[0]-1, cur_state[1], cur_state[2])
        if cur_state[-1] == 2:  # Left
            return (cur_state[0], cur_state[1]-1, cur_state[2])
        if cur_state[-1] == 3:  # Down
            return (cur_state[0]+1, cur_state[1], cur_state[2])
    elif motion == "R":  # Clockwise
        return (cur_state[0], cur_state[1], (cur_state[2]+3)%4)
    elif motion == "C":  # Counter-clockwise
        return (cur_state[0], cur_state[1], (cur_state[2]+1)%4)
    elif motion in ["W", "T"]:
        return cur_state
    else:
        print("Invalid motion")
        sys.exit()


def state_transition_mapf(cur_state:Tuple[int,int,int], motion:str) -> Tuple[int,int,int]:
    if motion == "U":  # south (down)
        return (cur_state[0]+1, cur_state[1], cur_state[2])
    if motion == "L": #west (left)
        return (cur_state[0], cur_state[1]-1, cur_state[2])
    if motion == "R": #east (right)
        return (cur_state[0], cur_state[1]+1, cur_state[2])
    if motion == "D": #north (up)
        return (cur_state[0]-1, cur_state[1], cur_state[2])
    if motion in ["W", "T"]:
        return cur_state
    print("Invalid motion")
    sys.exit()


@njit(cache=True)
def apply_motion_code(row, col, direction, motion, is_mapf, is_tick, ticks_per_timestep):
    if is_mapf:
        step = 1.0
        if is_tick:
            step = 1.0 / float(ticks_per_timestep)
        if motion == 0:
            row += step
        elif motion == 1:
            col -= step
        elif motion == 2:
            col += step
        elif motion == 3:
            row -= step
        return row, col, direction

    if motion == 0:
        if is_tick:
            frac = 1.0 / float(ticks_per_timestep)
            angle = direction * (math.pi / 2.0)
            row -= math.sin(angle) * frac
            col += math.cos(angle) * frac
        else:
            if direction == 0:
                col += 1.0
            elif direction == 1:
                row -= 1.0
            elif direction == 2:
                col -= 1.0
            else:
                row += 1.0
    elif motion == 1:
        if is_tick:
            direction = (direction - (1.0 / float(ticks_per_timestep))) % 4.0
        else:
            direction = (direction + 3.0) % 4.0
    elif motion == 2:
        if is_tick:
            direction = (direction + (1.0 / float(ticks_per_timestep))) % 4.0
        else:
            direction = (direction + 1.0) % 4.0

    return row, col, direction


@njit(parallel=True, cache=True)
def compute_exec_paths(motion_codes, starts, results, step_counts,
                       is_mapf, is_tick, ticks_per_timestep):
    for ag_id in prange(starts.shape[0]):
        num_steps = step_counts[ag_id]
        row = starts[ag_id, 0]
        col = starts[ag_id, 1]
        direction = starts[ag_id, 2]
        results[ag_id, 0, 0] = row
        results[ag_id, 0, 1] = col
        results[ag_id, 0, 2] = direction

        for i in range(num_steps):
            motion = motion_codes[ag_id, i]
            row, col, direction = apply_motion_code(
                row, col, direction, motion, is_mapf, is_tick, ticks_per_timestep
            )
            results[ag_id, i + 1, 0] = row
            results[ag_id, i + 1, 1] = col
            results[ag_id, i + 1, 2] = direction


@njit(parallel=True, cache=True)
def compute_plan_next_states(motion_codes, starts, base_states, results, step_counts,
                             is_mapf, is_tick, ticks_per_timestep):
    for ag_id in prange(starts.shape[0]):
        num_steps = step_counts[ag_id]
        start_row = starts[ag_id, 0]
        start_col = starts[ag_id, 1]
        start_direction = starts[ag_id, 2]
        results[ag_id, 0, 0] = start_row
        results[ag_id, 0, 1] = start_col
        results[ag_id, 0, 2] = start_direction

        for i in range(num_steps):
            row = base_states[ag_id, i, 0]
            col = base_states[ag_id, i, 1]
            direction = base_states[ag_id, i, 2]
            motion = motion_codes[ag_id, i]
            row, col, direction = apply_motion_code(
                row, col, direction, motion, is_mapf, is_tick, ticks_per_timestep
            )
            results[ag_id, i + 1, 0] = row
            results[ag_id, i + 1, 1] = col
            results[ag_id, i + 1, 2] = direction


class BaseObj:
    def __init__(self, _obj_, _text_, _loc_, _color_) -> None:
        self.obj = _obj_
        self.text = _text_
        self.loc = _loc_
        self.color = _color_


class Agent:
    def __init__(self, idx, ag_obj:BaseObj, st_obj:BaseObj, plan_pth:List,
                 pth_obj:List[BaseObj], exec_pth:List, dir_obj:BaseObj=None):
        self.idx = idx
        self.agent_obj = ag_obj
        self.start_obj = st_obj
        self.plan_path = plan_pth
        self.path_objs = pth_obj
        self.exec_path = exec_pth
        self.dir_obj = dir_obj  # Oval on canvas showing the direction of an agent
        self.path = self.exec_path  # Set execution path as default


class Task:
    def __init__(self, idx:int, loc:Tuple[int,int], task_obj: BaseObj,
                 assigned:Tuple[int,int]=(math.inf,math.inf),
                 finished:Tuple[int,int]=(math.inf,math.inf),
                 state:str="unassigned"):
        self.idx = idx
        self.loc = loc
        self.events = {"assigned": {"agent": assigned[0], "timestep": assigned[1]},
                       "finished": {"agent": finished[0], "timestep": finished[1]}}
        self.task_obj = task_obj
        self.state = state


class SequentialTask:
    def __init__(self, idx:int, tasks:List[Task], release_tstep:int=-1) -> None:
        self.idx = idx
        self.tasks = tasks
        self.release_tstep = release_tstep
