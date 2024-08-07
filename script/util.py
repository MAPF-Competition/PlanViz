# -*- coding: UTF-8 -*-
""" Utility functions
"""

import sys
import math
from typing import List, Tuple, Dict

TASK_COLORS: Dict[int, str] = {
    "unassigned": "#eeeaa2",
    "newlyassigned": "yellowgreen",
    "assigned": "orange",
    "finished": "grey"
}

AGENT_COLORS: Dict[str, str] = {
    "newlyassigned": "yellowgreen",
    "assigned": "deepskyblue",
    "collide": "red"
}

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
    if glob_dir == 0:
        out_angle = 0
    elif glob_dir == 1:
        out_angle = math.pi / 2.
    elif glob_dir == 2:
        out_angle = math.pi
    elif glob_dir == 3:
        out_angle = -1 * math.pi / 2.
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
    if motion == "D":  # south (down)
        return (cur_state[0]+1, cur_state[1], cur_state[2])
    if motion == "L": #west (left)
        return (cur_state[0], cur_state[1]-1, cur_state[2])
    if motion == "R": #east (right)
        return (cur_state[0], cur_state[1]+1, cur_state[2])
    if motion == "U": #north (up)
        return (cur_state[0]-1, cur_state[1], cur_state[2])
    if motion in ["W", "T"]:
        return cur_state
    print("Invalid motion")
    sys.exit()


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
