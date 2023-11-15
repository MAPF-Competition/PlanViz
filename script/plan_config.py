# -*- coding: UTF-8 -*-
""" Plan configurations with rotation agents
This script contains the configurations for PlanViz, a visualizer for the League of Robot Runners.
All rights reserved.
"""

import sys
import logging
from typing import List, Tuple, Dict, Set
import tkinter as tk
import json
import numpy as np
from util import TASK_COLORS, AGENT_COLORS, DIRECTION, OBSTACLES, MAP_CONFIG, \
    get_map_name, get_dir_loc, BaseObj, Agent, Task


class PlanConfig:
    """ Plan configuration and loading and rendering functions.
    """
    def __init__(self, map_file, plan_file, team_size, start_tstep, end_tstep, ppm, moves, delay):
        map_name = get_map_name(map_file)
        self.team_size:int = team_size
        self.start_tstep:int = start_tstep
        self.end_tstep:int = end_tstep

        self.agent_model:str = ""

        self.ppm:int = ppm
        if self.ppm is None:
            if map_name in MAP_CONFIG:
                self.ppm = MAP_CONFIG[map_name]["pixel_per_move"]
            else:
                raise TypeError("Missing variable: pixel_per_move.")
        self.moves = moves
        if self.moves is None:
            if map_name in MAP_CONFIG:
                self.moves = MAP_CONFIG[map_name]["moves"]
            else:
                raise TypeError("Missing variable: moves.")
        self.delay:int = delay
        if self.delay is None:
            if map_name in MAP_CONFIG:
                self.delay = MAP_CONFIG[map_name]["delay"]
            else:
                raise TypeError("Missing variable: delay.")

        self.tile_size:int = self.ppm * self.moves
        self.width:int = -1
        self.height:int = -1
        self.env_map:List[List[int]] = []
        self.grids:List = []
        self.tasks = {}
        self.events = {"assigned": {}, "finished": {}}
        self.event_tracker = {}

        self.start_loc  = {}
        self.plan_paths = {}
        self.exec_paths = {}
        self.conflicts  = {}
        self.agents:Dict[int,Agent] = {}
        self.ag_to_task:Dict[int, List[int]] = {}
        self.makespan:int = -1
        self.cur_timestep:int = self.start_tstep
        self.shown_path_agents:Set[int] = set()
        self.conflict_agents:Set[int] = set()

        self.load_map(map_file)  # Load from the map file

        # Initialize the window
        self.window = tk.Tk()

        # Show MAPF instance
        # Use width and height for scaling
        self.canvas = tk.Canvas(self.window,
                                width=(self.width+1) * self.tile_size,
                                height=(self.height+1) * self.tile_size,
                                bg="white")
        self.canvas.grid(row=0, column=0,sticky="nsew")
        self.canvas.configure(scrollregion = self.canvas.bbox("all"))

        # Render instance on canvas
        self.load_plan(plan_file)  # Load the results
        self.render_env()
        self.render_agents()


    def load_map(self, map_file:str) -> None:
        print("Loading map from " + map_file, end = '... ')

        with open(file=map_file, mode="r", encoding="UTF-8") as fin:
            fin.readline()  # ignore type
            self.height = int(fin.readline().strip().split(' ')[1])
            self.width  = int(fin.readline().strip().split(' ')[1])
            fin.readline()  # ignore 'map' line
            for line in fin.readlines():
                out_line: List[bool] = []
                for word in list(line.strip()):
                    if word in OBSTACLES:
                        out_line.append(0)
                    elif word in [".", "S"]:
                        out_line.append(1)
                    elif word == "E":
                        out_line.append(2)

                assert len(out_line) == self.width
                self.env_map.append(out_line)
        assert len(self.env_map) == self.height
        print("Done!")


    def load_paths(self, data:Dict):
        print("Loading paths", end="... ")

        state_trans = self.state_transition
        if self.agent_model == "MAPF":
            state_trans = self.state_transition_mapf
        for ag_id in range(self.team_size):
            start = data["start"][ag_id]  # Get start location
            start = (int(start[0]), int(start[1]), DIRECTION[start[2]])
            self.start_loc[ag_id] = start

            self.exec_paths[ag_id] = []  # Get actual path
            self.exec_paths[ag_id].append(start)
            if "actualPaths" in data:
                tmp_str = data["actualPaths"][ag_id].split(",")
                for motion in tmp_str:
                    next_ = state_trans(self.exec_paths[ag_id][-1], motion)
                    self.exec_paths[ag_id].append(next_)
                if self.makespan < max(len(self.exec_paths[ag_id])-1, 0):
                    self.makespan = max(len(self.exec_paths[ag_id])-1, 0)
            else:
                print("No actual paths.", end=" ")

            self.plan_paths[ag_id] = []  # Get planned path
            self.plan_paths[ag_id].append(start)
            if "plannerPaths" in data:
                tmp_str = data["plannerPaths"][ag_id].split(",")
                for tstep, motion in enumerate(tmp_str):
                    next_ = state_trans(self.exec_paths[ag_id][tstep], motion)
                    self.plan_paths[ag_id].append(next_)
            else:
                print("No planner paths.", end=" ")

        for ag_id in range(self.team_size):
            self.exec_paths[ag_id] = self.exec_paths[ag_id][self.start_tstep:self.end_tstep+1]
            self.plan_paths[ag_id] = self.plan_paths[ag_id][self.start_tstep:self.end_tstep+1]

        print("Done!")


    def load_errors(self, data:Dict):
        print("Loading errors", end="... ")
        if "errors" not in data:
            print("No errors.")
            return

        for err in data["errors"]:
            tstep = err[2]
            if self.start_tstep <= tstep <= self.end_tstep:
                self.conflict_agents.add(err[0])
                self.conflict_agents.add(err[1])
                if tstep not in self.conflicts:  # Sort errors according to the tstep
                    self.conflicts[tstep] = []
                self.conflicts[tstep].append(err)
        print("Done!")


    def load_events(self, data:Dict):
        print("Loading events", end="... ")

        if "events" not in data:
            print("No events.")
            return

        # Initialize assigned events
        ag_to_timedtasks = {}
        for ag_ in range(self.team_size):
            for eve in data["events"][ag_]:
                if eve[2] != "assigned":
                    continue
                tid:int   = eve[0]
                tstep:int = eve[1]
                if ag_ not in ag_to_timedtasks:
                    ag_to_timedtasks[ag_] = []
                ag_to_timedtasks[ag_].append((tid, tstep))

        for _, timedtasks in ag_to_timedtasks.items():
            timedtasks.sort(key=lambda x: x[1])
            st_id = 0
            ed_id = len(timedtasks)
            for ii in range(len(timedtasks)-1):
                if self.start_tstep < timedtasks[ii+1][-1]:
                    st_id = ii
                    break
            for ii in range(len(timedtasks)-1):
                if self.end_tstep < timedtasks[ii+1][-1]:
                    ed_id = ii
                    break
            timedtasks = timedtasks[st_id:ed_id]

        shown_tasks = set()
        for _, timedtasks in ag_to_timedtasks.items():
            for ttsk in timedtasks:
                shown_tasks.add(ttsk[0])

        # Initialize assigned events
        for ag_ in range(self.team_size):
            for eve in data["events"][ag_]:
                if eve[2] != "assigned":
                    continue
                tid:int   = eve[0]
                tstep:int = eve[1]
                if tid in shown_tasks:
                    if tstep not in self.events["assigned"]:
                        self.events["assigned"][tstep] = {}  # task_idx -> agent
                    self.events["assigned"][tstep][tid] = ag_
                    if ag_ not in self.ag_to_task:
                        self.ag_to_task[ag_] = []
                    self.ag_to_task[ag_].append(tid)
        self.event_tracker["aTime"] = list(sorted(self.events["assigned"].keys()))
        self.event_tracker["aTime"].append(-1)
        self.event_tracker["aid"] = 0

        # Initialize finished events
        for ag_ in range(self.team_size):
            for eve in data["events"][ag_]:
                if eve[2] != "finished":
                    continue
                tid:int   = eve[0]
                tstep:int = eve[1]
                if tid in shown_tasks:
                    if tstep not in self.events["finished"]:
                        self.events["finished"][tstep] = {}  # task_idx -> agent
                    self.events["finished"][tstep][tid] = ag_
        self.event_tracker["fTime"] = list(sorted(self.events["finished"].keys()))
        self.event_tracker["fTime"].append(-1)
        self.event_tracker["fid"] = 0
        print("Done!")


    def load_tasks(self, data:Dict):
        print("Loading tasks", end="... ")

        if "tasks" not in data:
            print("No tasks.")
            return

        if self.event_tracker:
            for a_time in self.event_tracker["aTime"]:  # traverse all assigned timesteps
                if a_time == -1:
                    continue
                for tid in self.events["assigned"][a_time]:
                    _task_ = data["tasks"][tid]
                    assert tid == _task_[0]
                    _tloc_ = (_task_[1], _task_[2])
                    _tobj_ = self.render_obj(tid, _tloc_, "rectangle", TASK_COLORS["unassigned"])
                    new_task = Task(tid, _tloc_, _tobj_)
                    self.tasks[tid] = new_task
        else:
            print("No events found. Render all tasks.", end=" ")
            for _, task_list in self.ag_to_task.items():
                for tid in task_list:
                    _task_ = data["tasks"][tid]
                    assert tid == _task_[0]
                    _tloc_ = (_task_[1], _task_[2])
                    _tobj_ = self.render_obj(tid, _tloc_, "rectangle",
                                                TASK_COLORS["unassigned"])
                    new_task = Task(tid, _tloc_, _tobj_)
                    self.tasks[tid] = new_task

        print("Done!")


    def load_plan(self, plan_file):
        data = {}
        with open(file=plan_file, mode="r", encoding="UTF-8") as fin:
            data = json.load(fin)

        if self.team_size == np.inf:
            self.team_size = data["teamSize"]

        if self.end_tstep == np.inf:
            if "makespan" not in data.keys():
                raise KeyError("Missing makespan!")
            self.end_tstep = data["makespan"]

        if self.agent_model == "":
            if 'actionModel' not in data.keys():
                raise KeyError("Missing action model!")
            self.agent_model = data['actionModel']

        self.load_paths(data)
        self.load_errors(data)
        self.load_events(data)
        self.load_tasks(data)


    def state_transition(self, cur_state:Tuple[int,int,int], motion:str) -> Tuple[int,int,int]:
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
            logging.error("Invalid motion")
            sys.exit()


    def state_transition_mapf(self, cur_state:Tuple[int,int,int], motion:str) -> Tuple[int,int,int]:
        if motion == "D":  # south (down)
            return (cur_state[0]+1, cur_state[1], cur_state[2])
        elif motion == "L": #west (left)
            return (cur_state[0], cur_state[1]-1, cur_state[2])
        elif motion == "R": #east (right)
            return (cur_state[0], cur_state[1]+1, cur_state[2])
        elif motion == "U": #north (up)
            return (cur_state[0]-1, cur_state[1], cur_state[2])
        elif motion in ["W", "T"]:
            return cur_state
        else:
            logging.error("Invalid motion")
            sys.exit()


    def render_obj(self, _idx_:int, _loc_:Tuple[int], _shape_:str="rectangle",
                   _color_:str="blue", _state_:str="normal", offset:float=0.05, _tag_:str="obj"):
        """Mark certain positions on the visualizer

        Args:
            _idx_ (int, required): The index of the object
            _loc_ (List, required): A list of locations on the map.
            _shape_ (str, optional): The shape of marked on each location. Defaults to "rectangle".
            _color_ (str, optional): The color of the mark. Defaults to "blue".
            _state_ (str, optional): Whether to show the object or not. Defaults to "normal"
        """
        _tmp_canvas_ = None
        if _shape_ == "rectangle":
            _tmp_canvas_ = self.canvas.create_rectangle((_loc_[1]+offset) * self.tile_size,
                                                        (_loc_[0]+offset) * self.tile_size,
                                                        (_loc_[1]+1-offset) * self.tile_size,
                                                        (_loc_[0]+1-offset) * self.tile_size,
                                                        fill=_color_,
                                                        tag=_tag_,
                                                        state=_state_,
                                                        outline="")
        elif _shape_ == "oval":
            _tmp_canvas_ = self.canvas.create_oval((_loc_[1]+offset) * self.tile_size,
                                                   (_loc_[0]+offset) * self.tile_size,
                                                   (_loc_[1]+1-offset) * self.tile_size,
                                                   (_loc_[0]+1-offset) * self.tile_size,
                                                   fill=_color_,
                                                   tag=_tag_,
                                                   state=_state_,
                                                   outline="")
        else:
            logging.error("Undefined shape.")
            sys.exit()

        _tmp_text_ = self.canvas.create_text((_loc_[1]+0.5)*self.tile_size,
                                            (_loc_[0]+0.5)*self.tile_size,
                                            text=str(_idx_),
                                            fill="black",
                                            tag=("text", _tag_),
                                            state=_state_,
                                            font=("Arial", int(self.tile_size // 2)))

        return BaseObj(_tmp_canvas_, _tmp_text_, _loc_, _color_)


    def render_env(self) -> None:
        print("Rendering the environment ... ", end="")
        # Render grids
        for rid in range(self.height):  # Render horizontal lines
            _line_ = self.canvas.create_line(0, rid * self.tile_size,
                                             self.width * self.tile_size, rid * self.tile_size,
                                             tags="grid",
                                             state= "normal",
                                             fill="grey")
            self.grids.append(_line_)
        for cid in range(self.width):  # Render vertical lines
            _line_ = self.canvas.create_line(cid * self.tile_size, 0,
                                             cid * self.tile_size, self.height * self.tile_size,
                                             tags="grid",
                                             state= "normal",
                                             fill="grey")
            self.grids.append(_line_)

        # Render features
        for rid, _cur_row_ in enumerate(self.env_map):
            for cid, _cur_ele_ in enumerate(_cur_row_):
                if _cur_ele_ == 0:  # obstacles
                    self.canvas.create_rectangle(cid * self.tile_size,
                                                 rid * self.tile_size,
                                                 (cid+1)*self.tile_size,
                                                 (rid+1)*self.tile_size,
                                                 state="disable",
                                                 fill="black")

        # Render coordinates
        for cid in range(self.width):
            self.canvas.create_text((cid+0.5)*self.tile_size,
                                    (self.height+0.5)*self.tile_size,
                                    text=str(cid),
                                    fill="black",
                                    tag="text",
                                    state="disable",
                                    font=("Arial", int(self.tile_size//2)))
        for rid in range(self.height):
            self.canvas.create_text((self.width+0.5)*self.tile_size,
                                    (rid+0.5)*self.tile_size,
                                    text=str(rid),
                                    fill="black",
                                    tag="text",
                                    state="disable",
                                    font=("Arial", int(self.tile_size//2)))
        self.canvas.create_line(self.width * self.tile_size, 0,
                                self.width * self.tile_size, self.height * self.tile_size,
                                state="disable",
                                fill="black")
        self.canvas.create_line(0, self.height * self.tile_size,
                                self.width * self.tile_size, self.height * self.tile_size,
                                state="disable",
                                fill="black")
        print("Done!")


    def render_agents(self):
        print("Rendering the agents... ", end="")
        # Separate the render of static locations and agents so that agents can overlap
        start_objs = []
        path_objs = []

        for ag_id in range(self.team_size):
            start = self.render_obj(ag_id, self.start_loc[ag_id], "oval", "grey", "disable")
            start_objs.append(start)

            ag_path = []  # Render paths as purple rectangles
            for _pid_ in range(len(self.exec_paths[ag_id])):
                _p_loc_ = (self.exec_paths[ag_id][_pid_][0], self.exec_paths[ag_id][_pid_][1])
                _p_obj = None
                if _pid_ > 0 and _p_loc_ == (self.exec_paths[ag_id][_pid_-1][0],
                                             self.exec_paths[ag_id][_pid_-1][1]):
                    _p_obj = self.render_obj(ag_id, _p_loc_, "rectangle", "purple", "disable", 0.25)
                else:  # non-wait action, smaller rectangle
                    _p_obj = self.render_obj(ag_id, _p_loc_, "rectangle", "purple", "disable", 0.4)
                if _p_obj is not None:
                    self.canvas.tag_lower(_p_obj.obj)
                    self.canvas.itemconfigure(_p_obj.obj, state="hidden")
                    self.canvas.delete(_p_obj.text)
                    ag_path.append(_p_obj)
            path_objs.append(ag_path)

        if len(self.exec_paths) == 0:
            raise ValueError("Missing actual paths!")

        for ag_id in range(self.team_size):  # Render the actual agents
            agent_obj = self.render_obj(ag_id, self.exec_paths[ag_id][0], "oval",
                                        AGENT_COLORS["assigned"], "disable", 0.05, str(ag_id))
            dir_obj = None
            if self.agent_model == "MAPF_T":
                dir_loc = get_dir_loc(self.exec_paths[ag_id][0])
                dir_obj = self.canvas.create_oval(dir_loc[0] * self.tile_size,
                                                dir_loc[1] * self.tile_size,
                                                dir_loc[2] * self.tile_size,
                                                dir_loc[3] * self.tile_size,
                                                fill="navy",
                                                tag="dir",
                                                state="disable",
                                                outline="")

            agent = Agent(ag_id, agent_obj, start_objs[ag_id], self.plan_paths[ag_id],
                          path_objs[ag_id], self.exec_paths[ag_id], dir_obj)
            self.agents[ag_id] = agent
        print("Done!")
