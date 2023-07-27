# -*- coding: UTF-8 -*-
import math
from enum import Enum
from typing import List, Tuple

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


class BaseObj:
    def __init__(self, _obj_, _text_, _loc_, _color_) -> None:
        self.obj = _obj_
        self.text = _text_
        self.loc = _loc_
        self.color = _color_

class Agent:
    def __init__(self, _idx_, _ag_obj_:BaseObj, _start_:BaseObj,
                 _plan_path_:List, _path_objs_:List[BaseObj], _exec_path_:List, _dir_obj_):
        self.idx = _idx_
        self.task_idx = -1
        self.agent_obj = _ag_obj_
        self.start_obj = _start_
        self.dir_obj = _dir_obj_  # oval on canvas
        self.plan_path = _plan_path_
        self.exec_path = _exec_path_
        self.path_objs = _path_objs_
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
