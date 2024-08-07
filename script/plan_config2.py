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
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize
from matplotlib import cm
from util import TASK_COLORS, AGENT_COLORS, DIRECTION, OBSTACLES, MAP_CONFIG,\
    INT_MAX, DBL_MAX, get_map_name, get_dir_loc, BaseObj, Agent, SequentialTask


class PlanConfig2:
    """ Plan configuration for loading and rendering functions

    This is for LORR 2025.
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

        self.grids:List = []
        self.start_loc  = {}
        self.plan_paths = {}
        self.exec_paths = {}
        self.conflicts  = {}
        self.agents:Dict[int, Agent] = {}
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


    def load_sequential_tasks(self, data:Dict):
        print("Loading tasks", end="...")

        if "tasks" not in data:
            print("No tasks.")
            return

        print("No events found. Render all tasks with released time inside.", end=" ")
        for task in data["tasks"]:  # Now we need to use the released time of each task
            tid = task[0]
            released_time = task[1]
            if released_time > self.end_tstep:
                continue
            task_locs = []
            loc_num = len(task[2])//2  # Number of locations (x-y pairs)
            for loc_id in range(loc_num):
                tloc = (task[2][loc_id * 2], task[2][loc_id * 2 + 1])
                task_locs.append(tloc)

                tobj = self.render_obj(tid, tloc, "rectangle", TASK_COLORS["unassigned"])
