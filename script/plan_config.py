# -*- coding: UTF-8 -*-
""" Plan configurations with rotation agents
This script contains the configurations for PlanViz, a visualizer for the League of Robot Runners.
All rights reserved.
"""

import os
import sys
import logging
from typing import List, Tuple, Dict, Set
import tkinter as tk
import json
import math
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize
from matplotlib import cm
from util import (
    TASK_COLORS, AGENT_COLORS, DIRECTION, OBSTACLES, MAP_CONFIG, INT_MAX, DBL_MAX,
    get_map_name, get_dir_loc, state_transition, state_transition_mapf,
    BaseObj, Agent, Task, SequentialTask)

class PlanConfig2023:
    """ Plan configuration for loading and rendering functions.
    """
    def __init__(self, map_file, plan_file, team_size, start_tstep, end_tstep,
                 ppm, moves, delay, heat_maps, hwy_file, search_tree_files, heu_file):
        print("===== Initialize PlanConfig =====")

        map_name = get_map_name(map_file)
        self.team_size:int = team_size
        self.start_tstep:int = start_tstep
        self.end_tstep:int = end_tstep

        self.agent_model:str = ""

        self.width:int = -1
        self.height:int = -1
        self.env_map:List[List[int]] = []
        self.heat_map:List[List[int]] = []
        self.heuristic_map:List[List] = []
        self.search_trees:Dict[str, List[List[int]]] = {}
        self.highway:List[Dict[str, Tuple[int]]] = []
        self.tasks = {}
        self.events = {"assigned": {}, "finished": {}}
        self.event_tracker = {}

        self.grids:List = []
        self.heat_grids:List = []
        self.heuristic_grids:List = []
        self.search_tree_grids:Dict[str, List] = {}
        self.start_loc  = {}
        self.plan_paths = {}
        self.exec_paths = {}
        self.conflicts  = {}
        self.agents:Dict[int, Agent] = {}
        self.ag_to_task:Dict[int, List[int]] = {}
        self.makespan:int = -1
        self.cur_tstep:int = self.start_tstep
        self.shown_path_agents:Set[int] = set()
        self.conflict_agents:Set[int] = set()
        self.cur_tree:str = "None"

        self.load_map(map_file)  # Load from the map file

        # Initialize the window
        self.window = tk.Tk()

        self.screen_width = self.window.winfo_screenwidth()

        pixel_per_grid = (self.screen_width - 25) // (self.width + 1)

        self.moves = moves
        if self.moves is None:
            if map_name in MAP_CONFIG:
                self.moves = MAP_CONFIG[map_name]["moves"]
            else:
                self.moves = 3
        
        self.ppm:int = ppm
        if self.ppm is None:
            if map_name in MAP_CONFIG:
                self.ppm = MAP_CONFIG[map_name]["pixel_per_move"]
            else:
                self.ppm = pixel_per_grid // self.moves

        self.delay:int = delay
        if self.delay is None:
            if map_name in MAP_CONFIG:
                self.delay = MAP_CONFIG[map_name]["delay"]
            else:
                self.delay = 0.06
        self.tile_size:int = self.ppm * self.moves


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
        self.load_heat_maps(heat_maps)  # Load heat map with exec_paths and others json files
        self.load_highway(hwy_file)
        self.load_search_trees(search_tree_files)
        self.load_heuristic_map(heu_file, 104)
        self.render_env()
        self.render_heat_map()
        self.render_highway()
        self.render_heuristic_map()
        self.render_search_trees()
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

        state_trans = state_transition
        if self.agent_model == "MAPF":
            state_trans = state_transition_mapf
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

        # Load all the assigned events
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

        for _, timedtasks in ag_to_timedtasks.items():  # Extract tasks between start and end timesteps
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
                    task = data["tasks"][tid]
                    assert tid == task[0]
                    tloc = (task[1], task[2])
                    tobj = self.render_obj(tid, tloc, "rectangle", TASK_COLORS["unassigned"])
                    new_task = Task(tid, tloc, tobj)
                    self.tasks[tid] = new_task
        else:
            print("No events found. Render all tasks.", end=" ")
            for _, task_list in self.ag_to_task.items():
                for tid in task_list:
                    task = data["tasks"][tid]
                    assert tid == task[0]
                    tloc = (task[1], task[2])
                    tobj = self.render_obj(tid, tloc, "rectangle", TASK_COLORS["unassigned"])
                    new_task = Task(tid, tloc, tobj)
                    self.tasks[tid] = new_task

        print("Done!")


    def load_plan(self, plan_file):
        data = {}
        with open(file=plan_file, mode="r", encoding="UTF-8") as fin:
            data = json.load(fin)

        self.team_size = min(data["teamSize"], self.team_size)

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


    def load_heat_maps(self, plan_files:List[str]):
        if not plan_files:  # plan_files is empty
            return

        self.heat_map = [[0 for _ in range(self.width)] for _ in range(self.height)]
        for plan_file in plan_files:
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

            state_trans = state_transition
            if self.agent_model == "MAPF":
                state_trans = state_transition_mapf

            for ag_id in range(data["teamSize"]):
                start = data["start"][ag_id]  # Get start location
                start = (int(start[0]), int(start[1]), DIRECTION[start[2]])

                exec_path = []  # Get actual path
                exec_path.append(start)
                if "actualPaths" in data:
                    tmp_str = data["actualPaths"][ag_id].split(",")
                    for motion in tmp_str:
                        next_ = state_trans(exec_path[-1], motion)
                        exec_path.append(next_)

                    path_cost = len(exec_path) - 1
                    while tmp_str[path_cost-1] == "W":
                        path_cost -= 1
                        if path_cost == 0:
                            break
                else:
                    print("No actual paths.", end=" ")

                for tt in range(path_cost):
                    p = exec_path[tt]
                    self.heat_map[p[0]][p[1]] += 1


    def load_heuristic_map(self, heu_file:str, ag:int):
        if heu_file == "":
            return

        with open(heu_file, mode="r", encoding="UTF-8") as fin:
            self.heuristic_map = [[0 for _ in range(self.width)] for _ in range(self.height)]
            for _ in range(0, ag):
                fin.readline()
            line = fin.readline().strip().split(",")
            assert int(line[0]) == ag
            assert len(line) == self.width * self.height + 1
            for i in range(1, len(line)):
                loc = i - 1
                row = loc // self.width
                col = loc % self.width
                self.heuristic_map[row][col] = float(line[i])


    def load_highway(self, hwy_file:str):
        if hwy_file == "":
            return

        edge_num:int = 0  # Number of edges in the highway
        with open(file=hwy_file, mode="r", encoding="utf-8") as fin:
            edge_num = int(fin.readline().strip())
            for line in fin.readlines():
                edge_idx = int(line.strip())
                _from_ = (edge_idx // (self.width * self.height)) - 1
                from_row = _from_ // self.width
                from_col = _from_ % self.width
                _to_ = edge_idx % (self.width * self.height)
                to_row = _to_ // self.width
                to_col = _to_ % self.width
                assert (from_row == to_row) or (from_col == to_col)
                self.highway.append({"from":(from_row, from_col), "to":(to_row, to_col)})
            assert len(self.highway) == edge_num


    def load_search_trees(self, search_tree_files:List[str]):
        if not search_tree_files:
            return

        print("Loading search trees... ", end="")
        for fin in search_tree_files:
            search_map = [[0 for _ in range(self.width)] for _ in range(self.height)]
            if os.path.exists(fin):
                data_frame = pd.read_csv(fin)
                for _, data_row in data_frame.iterrows():
                    row = data_row["loc"] // self.width
                    col = data_row["loc"] % self.width
                    search_map[row][col] += 1
            file_name = fin.split("/")[-1].split(".")[0]
            if file_name not in self.search_trees:
                self.search_trees[file_name] = search_map
        print("Done!")


    def render_obj(self, _idx_:int, _loc_:Tuple[int], _shape_:str="rectangle",
                   _color_:str="blue", _state_=tk.NORMAL,
                   offset:float=0.05, _tag_:str="obj", _outline_:str=""):
        """Mark certain positions on the visualizer

        Args:
            _idx_ (int, required): The index of the object
            _loc_ (List, required): A list of locations on the map.
            _shape_ (str, optional): The shape of marked on each location. Defaults to "rectangle".
            _color_ (str, optional): The color of the mark. Defaults to "blue".
            _state_ (str, optional): Whether to show the object or not. Defaults to tk.NORMAL
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
                                                        outline=_outline_)
        elif _shape_ == "oval":
            _tmp_canvas_ = self.canvas.create_oval((_loc_[1]+offset) * self.tile_size,
                                                   (_loc_[0]+offset) * self.tile_size,
                                                   (_loc_[1]+1-offset) * self.tile_size,
                                                   (_loc_[0]+1-offset) * self.tile_size,
                                                   fill=_color_,
                                                   tag=_tag_,
                                                   state=_state_,
                                                   outline=_outline_)
        else:
            logging.error("Undefined shape.")
            sys.exit()

        # shown_text = ""
        # if _idx_ > -1:
        #     shown_text = str(_idx_)
        shown_text = str(_idx_)
        _tmp_text_ = self.canvas.create_text((_loc_[1]+0.5)*self.tile_size,
                                            (_loc_[0]+0.5)*self.tile_size,
                                            text=shown_text,
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
                                             state= tk.NORMAL,
                                             fill="grey")
            self.grids.append(_line_)
        for cid in range(self.width):  # Render vertical lines
            _line_ = self.canvas.create_line(cid * self.tile_size, 0,
                                             cid * self.tile_size, self.height * self.tile_size,
                                             tags="grid",
                                             state= tk.NORMAL,
                                             fill="grey")
            self.grids.append(_line_)

        # Render features
        for rid, cur_row in enumerate(self.env_map):
            for cid, cur_ele in enumerate(cur_row):
                if cur_ele == 0:  # obstacles
                    self.canvas.create_rectangle(cid * self.tile_size,
                                                 rid * self.tile_size,
                                                 (cid+1) * self.tile_size,
                                                 (rid+1) * self.tile_size,
                                                 state=tk.DISABLED,
                                                 outline="",
                                                 fill="black")

        # Render coordinates
        for cid in range(self.width):
            self.canvas.create_text((cid+0.5)*self.tile_size,
                                    (self.height+0.5)*self.tile_size,
                                    text=str(cid),
                                    fill="black",
                                    tag="text",
                                    state=tk.DISABLED,
                                    font=("Arial", int(self.tile_size//2)))
        for rid in range(self.height):
            self.canvas.create_text((self.width+0.5)*self.tile_size,
                                    (rid+0.5)*self.tile_size,
                                    text=str(rid),
                                    fill="black",
                                    tag="text",
                                    state=tk.DISABLED,
                                    font=("Arial", int(self.tile_size//2)))
        self.canvas.create_line(self.width * self.tile_size, 0,
                                self.width * self.tile_size, self.height * self.tile_size,
                                state=tk.DISABLED,
                                fill="black")
        self.canvas.create_line(0, self.height * self.tile_size,
                                self.width * self.tile_size, self.height * self.tile_size,
                                state=tk.DISABLED,
                                fill="black")
        print("Done!")


    def render_heat_map(self):
        if not self.heat_map:
            return

        print("Rendering the heatmap... ", end="")
        min_val = np.inf
        for cur_row in self.heat_map:
            for cur_ele in cur_row:
                if cur_ele < min_val:
                    min_val = cur_ele

        max_val = -np.inf
        for cur_row in self.heat_map:
            for cur_ele in cur_row:
                if cur_ele > max_val:
                    max_val = cur_ele

        cmap = cm.get_cmap("Reds")
        norm = Normalize(vmin=0, vmax=max_val)
        rgba = cmap(norm(self.heat_map))
        for rid, cur_row in enumerate(self.heat_map):
            for cid, cur_ele in enumerate(cur_row):
                if cur_ele <= 0:
                    continue
                cur_color = (int(rgba[rid][cid][0] * 255),
                             int(rgba[rid][cid][1] * 255),
                             int(rgba[rid][cid][2] * 255))
                _code = '#%02x%02x%02x' % cur_color
                _heat_obj = self.render_obj(cur_ele, (rid,cid), "rectangle", _code, tk.HIDDEN,
                                            0.0, "heatmap", "grey")
                self.heat_grids.append(_heat_obj)
        print("Done!")


    def render_highway(self):
        if not self.highway:
            return

        print("Rendering the highway... ", end="")
        HWY_DIRECTION = {(1,0): "↓",  # Down
                         (0,1): "→",  # Right
                         (-1,0): "↑", # Up
                         (0,-1): "←"} # Left
        for edge in self.highway:
            hdir = (edge["to"][0]-edge["from"][0],
                    edge["to"][1]-edge["from"][1])
            hdir = HWY_DIRECTION[hdir]
            loc = ((edge["to"][0]+edge["from"][0])/2.,
                   (edge["to"][1]+edge["from"][1])/2.)
            edge["obj"] = self.canvas.create_text((loc[1]+0.5) * self.tile_size,
                                                  (loc[0]+0.5) * self.tile_size,
                                                  text=hdir,
                                                  fill="red",
                                                  tag="hwy",
                                                  state=tk.HIDDEN,
                                                  font=("Arial", int(self.tile_size)))
        print("Done!")


    def render_heuristic_map(self):
        if not self.heuristic_map:
            return

        print("Rendering the heuristic map... ", end="")
        max_val = -np.inf
        for cur_row in self.heuristic_map:
            for cur_ele in cur_row:
                if cur_ele in [DBL_MAX, INT_MAX]:
                    continue
                if cur_ele > max_val:
                    max_val = cur_ele

        min_val = np.inf
        for cur_row in self.heuristic_map:
            for cur_ele in cur_row:
                if cur_ele in [DBL_MAX, INT_MAX]:
                    continue
                if cur_ele < min_val:
                    min_val = cur_ele

        cmap = cm.get_cmap("Greys")
        norm = Normalize(vmin=min_val, vmax=max_val)
        for rid, cur_row in enumerate(self.heuristic_map):
            for cid, cur_ele in enumerate(cur_row):
                if cur_ele in [DBL_MAX, INT_MAX]:
                    continue
                cur_rgba = cmap(norm(self.heuristic_map[rid][cid]))
                cur_color = (int(cur_rgba[0] * 255),
                             int(cur_rgba[1] * 255),
                             int(cur_rgba[2] * 255))
                _code = '#%02x%02x%02x' % cur_color
                _obj = self.render_obj(int(np.around(cur_ele)), (rid,cid), "rectangle", _code,
                                       tk.HIDDEN, 0.0, "heuristic", "grey")
                self.heuristic_grids.append(_obj)
        print("Done!")


    def render_search_trees(self):
        if not self.search_trees:
            return

        print("Rendering the search trees... ", end="")
        # Render search trees
        min_val = np.inf
        max_val = -np.inf
        for _, search_tree in self.search_trees.items():
            for cur_row in search_tree:
                for cur_ele in cur_row:
                    if cur_ele < min_val:
                        min_val = cur_ele
                    if cur_ele > max_val:
                        max_val = cur_ele
        cmap = cm.get_cmap("Blues")
        norm = Normalize(vmin=min_val, vmax=max_val)

        for ag_id, search_tree in self.search_trees.items():
            rgba = cmap(norm(search_tree))
            self.search_tree_grids[ag_id] = []
            for rid, cur_row in enumerate(search_tree):
                for cid, cur_ele in enumerate(cur_row):
                    if cur_ele > 0:
                        cur_color = (int(rgba[rid][cid][0] * 255),
                                     int(rgba[rid][cid][1] * 255),
                                     int(rgba[rid][cid][2] * 255))
                        _code = '#%02x%02x%02x' % cur_color
                        _obj = self.render_obj(-1, (rid,cid), "rectangle", _code, tk.HIDDEN,
                                               0.0, "search_tree")  # 0.05
                        self.search_tree_grids[ag_id].append(_obj)
        print("Done!")


    def render_agents(self):
        print("Rendering the agents... ", end="")
        # Separate the render of static locations and agents so that agents can overlap
        start_objs = []
        path_objs = []

        for ag_id in range(self.team_size):
            start = self.render_obj(ag_id, self.start_loc[ag_id], "oval", "grey", tk.DISABLED)
            start_objs.append(start)

            ag_path = []  # Render paths as purple rectangles
            for _pid_ in range(len(self.exec_paths[ag_id])):
                p_loc = (self.exec_paths[ag_id][_pid_][0], self.exec_paths[ag_id][_pid_][1])
                p_obj = None
                if _pid_ > 0 and p_loc == (self.exec_paths[ag_id][_pid_-1][0],
                                             self.exec_paths[ag_id][_pid_-1][1]):
                    p_obj = self.render_obj(ag_id, p_loc, "rectangle", "purple", tk.DISABLED, 0.25)
                else:  # non-wait action, smaller rectangle
                    p_obj = self.render_obj(ag_id, p_loc, "rectangle", "purple", tk.DISABLED, 0.4)
                if p_obj is not None:
                    self.canvas.tag_lower(p_obj.obj)
                    self.canvas.itemconfigure(p_obj.obj, state=tk.HIDDEN)
                    self.canvas.delete(p_obj.text)
                    ag_path.append(p_obj)
            path_objs.append(ag_path)

        if self.team_size != len(self.exec_paths):
            raise ValueError("Missing actual paths!")

        for ag_id in range(self.team_size):  # Render the actual agents
            agent_obj = self.render_obj(ag_id, self.exec_paths[ag_id][0], "oval",
                                        AGENT_COLORS["assigned"], tk.DISABLED, 0.05, str(ag_id))
            dir_obj = None
            if self.agent_model == "MAPF_T":
                dir_loc = get_dir_loc(self.exec_paths[ag_id][0])
                dir_obj = self.canvas.create_oval(dir_loc[0] * self.tile_size,
                                                dir_loc[1] * self.tile_size,
                                                dir_loc[2] * self.tile_size,
                                                dir_loc[3] * self.tile_size,
                                                fill="navy",
                                                tag="dir",
                                                state=tk.DISABLED,
                                                outline="")

            agent = Agent(ag_id, agent_obj, start_objs[ag_id], self.plan_paths[ag_id],
                          path_objs[ag_id], self.exec_paths[ag_id], dir_obj)
            self.agents[ag_id] = agent
        print("Done!")



class PlanConfig2024:
    """ Plan configuration for loading and rendering functions

    This is for LORR 2025, and I am like a clown (not even a joker).
    """
    def __init__(self, map_file, plan_file, team_size, start_tstep, end_tstep,
                 ppm, moves, delay):
        print("===== Initialize PlanConfig2 =====")

        map_name = get_map_name(map_file)
        self.team_size:int = team_size
        self.start_tstep:int = start_tstep
        self.end_tstep:int = end_tstep

        self.agent_model:str = ""

        self.width:int = -1
        self.height:int = -1
        self.env_map:List[List[int]] = []

        self.max_seq_num = -1
        self.seq_tasks:Dict[int, SequentialTask] = {}
        self.events:Dict[str, Dict[int, Dict[int,int]]] = {"assigned": {}, "finished": {}}
        self.event_tracker = {"aTime": [], "aid": 0, "fTime": [], "fid": 0}
        self.actual_schedule:Dict[int, List[Tuple[int]]] = {}  # timestep -> (task id, agent id)

        self.grids:List = []
        self.start_loc  = {}
        self.plan_paths = {}
        self.exec_paths = {}
        self.conflicts  = {}
        self.agent_assigned_task = {}
        self.agent_shown_task_arrow = {}
        self.agents:Dict[int, Agent] = {}
        self.makespan:int = -1
        self.cur_tstep:int = self.start_tstep
        self.shown_path_agents:Set[int] = set()
        self.shown_tasks_seq:Set[int] = set()
        self.conflict_agents:Set[int] = set()

        self.load_map(map_file)  # Load from the map file
        
        # Initialize the window
        self.window = tk.Tk()

        self.screen_width = self.window.winfo_screenwidth()

        pixel_per_grid = (self.screen_width - 25) // (self.width + 1)


        self.moves = moves
        if self.moves is None:
            if map_name in MAP_CONFIG:
                self.moves = MAP_CONFIG[map_name]["moves"]
            else:
                self.moves = 3
        
        self.ppm:int = ppm
        if self.ppm is None:
            if map_name in MAP_CONFIG:
                self.ppm = MAP_CONFIG[map_name]["pixel_per_move"]
            else:
                self.ppm = pixel_per_grid // self.moves

        self.delay:int = delay
        if self.delay is None:
            if map_name in MAP_CONFIG:
                self.delay = MAP_CONFIG[map_name]["delay"]
            else:
                self.delay = 0.06
        self.tile_size:int = self.ppm * self.moves

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
        # self.load_errors()

        # Render instance on canvas
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

        state_trans = state_transition
        if self.agent_model == "MAPF":
            state_trans = state_transition_mapf
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

        # Slice the paths according to the start and end timestep
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


    def load_schedule(self, data:Dict):
        print("Loading schedule", end="...")

        if "actualSchedule" not in data:
            print("No actualSchedule.")
            return

        for ag_id, schedule in enumerate(data["actualSchedule"]):
            self.agent_assigned_task[ag_id] = []
            self.agent_shown_task_arrow[ag_id] = []
            for ele in schedule.split(","):
                assign_tstep = int(ele.split(":")[0])
                if assign_tstep > self.end_tstep:
                    continue
                task_id = int(ele.split(":")[1])
                if task_id == -1:
                    continue
                if assign_tstep not in self.actual_schedule:
                    self.actual_schedule[assign_tstep] = []
                self.actual_schedule[assign_tstep].append((task_id, ag_id))
                self.agent_assigned_task[ag_id].append((assign_tstep, task_id))
                # Only consider the maximum assign timestep
                assert task_id in self.seq_tasks
                if self.seq_tasks[task_id].tasks[0].events["assigned"]["timestep"] != math.inf and \
                    assign_tstep <= self.seq_tasks[task_id].tasks[0].events["assigned"]["timestep"]:
                    continue

                for seq_id, _ in enumerate(self.seq_tasks[task_id].tasks):
                    global_task_id = self.max_seq_num * task_id + seq_id
                    if assign_tstep not in self.events["assigned"]:
                        self.events["assigned"][assign_tstep] = {}
                    self.events["assigned"][assign_tstep][global_task_id] = ag_id
                    self.seq_tasks[task_id].tasks[seq_id].events["assigned"]["agent"] = ag_id
                    self.seq_tasks[task_id].tasks[seq_id].events["assigned"]["timestep"] = assign_tstep
        self.event_tracker["aTime"] = list(sorted(self.events["assigned"].keys()))
        self.event_tracker["aTime"].append(-1)


    def load_events(self, data:Dict):
        print("Loading event", end="...")

        assert self.max_seq_num > -1
        for (finish_tstep, ag_id, task_id, nxt_errand_id) in data["events"]:
            if (finish_tstep > self.end_tstep):
                continue
            seq_id = nxt_errand_id - 1
            global_task_id = self.max_seq_num * task_id + seq_id
            if finish_tstep not in self.events["finished"]:
                self.events["finished"][finish_tstep] = {}      
            self.events["finished"][finish_tstep][global_task_id] = ag_id
            self.seq_tasks[task_id].tasks[seq_id].events["finished"]["agent"] = ag_id
            self.seq_tasks[task_id].tasks[seq_id].events["finished"]["timestep"] = finish_tstep
        self.event_tracker["fTime"] = list(sorted(self.events["finished"].keys()))
        self.event_tracker["fTime"].append(-1)


    def load_sequential_tasks(self, data:Dict):
        print("Loading tasks", end="...")
        self.grid2task = {}
        
        if "tasks" not in data:
            print("No tasks.")
            return
        
        
        assert self.max_seq_num == -1
        for task in data["tasks"]:  # Now we need to use the released time of each task
            tid = task[0]
            release_tstep = task[1]
            if release_tstep > self.end_tstep:
                continue
            tasks = []
            loc_num = len(task[2])//2  # Number of locations (x-y pairs)
            for loc_id in range(loc_num):
                tloc = (task[2][loc_id * 2], task[2][loc_id * 2 + 1])
                tobj = self.render_obj(
                    tid, tloc, "rectangle", TASK_COLORS["unassigned"], tk.DISABLED, 0, str(tid)
                )
                if not (tloc in self.grid2task.keys()):
                    self.grid2task[tobj.obj] = []
                self.grid2task[tobj.obj].append(tid)
                tasks.append(Task(tid, tloc, tobj))
            self.seq_tasks[tid] = SequentialTask(tid, tasks, release_tstep)
            self.max_seq_num = max(self.max_seq_num, len(tasks))
        print("Done!")


    def load_plan(self, plan_file):
        data = {}
        with open(file=plan_file, mode="r", encoding="UTF-8") as fin:
            data = json.load(fin)

        if self.team_size == math.inf:
            self.team_size = data["teamSize"]

        if self.end_tstep == math.inf:
            if "makespan" not in data.keys():
                raise KeyError("Missing makespan!")
            self.end_tstep = data["makespan"]

        if self.agent_model == "":
            if 'actionModel' not in data.keys():
                raise KeyError("Missing action model!")
            self.agent_model = data['actionModel']

        self.load_paths(data)
        self.load_errors(data)
        self.load_sequential_tasks(data)
        self.load_schedule(data)
        self.load_events(data)


    def render_obj(self, idx:int, loc:Tuple[int], shape:str="rectangle",
                   color:str="blue", state=tk.NORMAL,
                   offset:float=0.05, tag:str="obj", outline:str=""):
        """Mark certain positions on the visualizer

        Args:
            idx (int, required): The index of the object
            loc (List, required): A list of locations on the map.
            shape (str, optional): The shape of marked on each location. Defaults to "rectangle".
            color (str, optional): The color of the mark. Defaults to "blue".
            state (str, optional): Whether to show the object or not. Defaults to tk.NORMAL
        """
        tmp_canvas = None
        if shape == "rectangle":
            tmp_canvas = self.canvas.create_rectangle((loc[1]+offset)*self.tile_size,
                                                      (loc[0]+offset)*self.tile_size,
                                                      (loc[1]+1-offset)*self.tile_size,
                                                      (loc[0]+1-offset)*self.tile_size,
                                                      fill=color,
                                                      tag=tag,
                                                      state=state,
                                                      outline=outline)
        elif shape == "oval":
            tmp_canvas = self.canvas.create_oval((loc[1]+offset)*self.tile_size,
                                                 (loc[0]+offset)*self.tile_size,
                                                 (loc[1]+1-offset)*self.tile_size,
                                                 (loc[0]+1-offset)*self.tile_size,
                                                 fill=color,
                                                 tag=tag,
                                                 state=state,
                                                 outline=outline)
        else:
            logging.error("Undefined shape.")
            sys.exit()

        shown_text = ""
        if idx > -1:
            shown_text = str(idx)
        tmp_text = self.canvas.create_text((loc[1]+0.5)*self.tile_size,
                                           (loc[0]+0.5)*self.tile_size,
                                           text=shown_text,
                                           fill="black",
                                           tag=("text", tag),
                                           state=state,
                                           font=("Arial", int(self.tile_size // 2)))

        return BaseObj(tmp_canvas, tmp_text, loc, color)


    def render_env(self) -> None:
        print("Rendering the environment ... ", end="")
        # Render grids
        for rid in range(self.height):  # Render horizontal lines
            _line_ = self.canvas.create_line(0,
                                             rid * self.tile_size,
                                             self.width * self.tile_size,
                                             rid * self.tile_size,
                                             tags="grid",
                                             state= tk.NORMAL,
                                             fill="grey")
            self.grids.append(_line_)
        for cid in range(self.width):  # Render vertical lines
            _line_ = self.canvas.create_line(cid * self.tile_size,
                                             0,
                                             cid * self.tile_size,
                                             self.height * self.tile_size,
                                             tags="grid",
                                             state= tk.NORMAL,
                                             fill="grey")
            self.grids.append(_line_)

        # Render features
        for rid, cur_row in enumerate(self.env_map):
            for cid, cur_ele in enumerate(cur_row):
                if cur_ele == 0:  # obstacles
                    self.canvas.create_rectangle(cid * self.tile_size,
                                                 rid * self.tile_size,
                                                 (cid+1) * self.tile_size,
                                                 (rid+1) * self.tile_size,
                                                 state=tk.DISABLED,
                                                 outline="",
                                                 fill="black")

        # Render coordinates
        for cid in range(self.width):
            self.canvas.create_text((cid+0.5)*self.tile_size,
                                    (self.height+0.5)*self.tile_size,
                                    text=str(cid),
                                    fill="black",
                                    tag="text",
                                    state=tk.DISABLED,
                                    font=("Arial", self.tile_size//2))
        for rid in range(self.height):
            self.canvas.create_text((self.width+0.5)*self.tile_size,
                                    (rid+0.5)*self.tile_size,
                                    text=str(rid),
                                    fill="black",
                                    tag="text",
                                    state=tk.DISABLED,
                                    font=("Arial", self.tile_size//2))
        self.canvas.create_line(self.width * self.tile_size,
                                0,
                                self.width * self.tile_size,
                                self.height * self.tile_size,
                                state=tk.DISABLED,
                                fill="black")
        self.canvas.create_line(0,
                                self.height * self.tile_size,
                                self.width * self.tile_size,
                                self.height * self.tile_size,
                                state=tk.DISABLED,
                                fill="black")
        print("Done!")


    def render_agents(self):
        print("Rendering the agents... ", end="")
        # Separate the render of static locations and agents so that agents can overlap
        start_objs = []
        path_objs = []

        for ag_id in range(self.team_size):
            start = self.render_obj(ag_id, self.start_loc[ag_id], "oval", "grey", tk.DISABLED)
            start_objs.append(start)

            ag_path = []  # Render paths as purple rectangles
            for _pid_ in range(len(self.exec_paths[ag_id])):
                p_loc = (self.exec_paths[ag_id][_pid_][0], self.exec_paths[ag_id][_pid_][1])
                p_obj = None
                if _pid_ > 0 and p_loc == (self.exec_paths[ag_id][_pid_-1][0],
                                           self.exec_paths[ag_id][_pid_-1][1]):
                    p_obj = self.render_obj(ag_id, p_loc, "rectangle", "purple", tk.DISABLED, 0.25)
                else:  # non-wait action, smaller rectangle
                    p_obj = self.render_obj(ag_id, p_loc, "rectangle", "purple", tk.DISABLED, 0.4)
                if p_obj is not None:
                    self.canvas.tag_lower(p_obj.obj)
                    self.canvas.itemconfigure(p_obj.obj, state=tk.HIDDEN)
                    self.canvas.delete(p_obj.text)
                    ag_path.append(p_obj)
            path_objs.append(ag_path)

        if self.team_size != len(self.exec_paths):
            raise ValueError("Missing actual paths!")

        for ag_id in range(self.team_size):  # Render the actual agents
            agent_obj = self.render_obj(ag_id, self.exec_paths[ag_id][0], "oval",
                                        AGENT_COLORS["assigned"], tk.DISABLED, 0.05, str(ag_id))
            dir_obj = None
            if self.agent_model == "MAPF_T":
                dir_loc = get_dir_loc(self.exec_paths[ag_id][0])
                dir_obj = self.canvas.create_oval(dir_loc[0] * self.tile_size,
                                                dir_loc[1] * self.tile_size,
                                                dir_loc[2] * self.tile_size,
                                                dir_loc[3] * self.tile_size,
                                                fill="navy",
                                                tag="dir",
                                                state=tk.DISABLED,
                                                outline="")

            agent = Agent(ag_id, agent_obj, start_objs[ag_id], self.plan_paths[ag_id],
                          path_objs[ag_id], self.exec_paths[ag_id], dir_obj)
            self.agents[ag_id] = agent
        print("Done!")
