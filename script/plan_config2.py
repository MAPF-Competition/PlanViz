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
import math
from util import\
    TASK_COLORS, AGENT_COLORS, DIRECTION, OBSTACLES, MAP_CONFIG,\
    get_map_name, get_dir_loc, state_transition, state_transition_mapf,\
    BaseObj, Agent, Task, SequentialTask


class PlanConfig2:
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
