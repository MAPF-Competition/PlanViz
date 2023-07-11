# -*- coding: UTF-8 -*-
""" Plan Visualizer with rotation agents
This is a script for visualizing the plan for MAPF.
"""

import sys
import logging
import argparse
import math
from typing import List, Tuple, Dict
import tkinter as tk
from tkinter import ttk
import time
import json
import numpy as np
from util import *

TASK_COLORS: Dict[str, str] = {"unassigned": "orange", "assigned": "pink", "finished": "grey"}
DIRECTION: Dict[str,int] = {"E":0, "S":1, "W":2, "N":3}
OBSTACLES: List[str] = ['@', 'T']

MAP_CONFIG: Dict[str,Dict] = {
    "Paris_1_256": {"pixel_per_move": 2, "moves": 2, "delay": 0.06},
    "brc202d": {"pixel_per_move": 2, "moves": 2, "delay": 0.06},
    "random-32-32-20": {"pixel_per_move": 5, "moves": 5, "delay": 0.06},
    "warehouse_large": {"pixel_per_move": 2, "moves": 2, "delay": 0.06},
    "warehouse_small": {"pixel_per_move": 5, "moves": 5, "delay": 0.06},
    "sortation_large": {"pixel_per_move": 2, "moves": 2, "delay": 0.06}
}

DIR_DIAMETER = 0.1
DIR_OFFSET = 0.05

sin = lambda degs: math.sin(math.radians(degs))
cos = lambda degs: math.cos(math.radians(degs))


class PlanVis:
    """Render MAPF instance
    """
    def __init__(self, in_arg) -> None:
        print("===== Initialize MAPF visualizer =====")

        # Load the yaml file or the input arguments
        self.map_file:str = in_arg.map
        map_name = get_map_name(self.map_file)
        self.plan_file:str = in_arg.plan
        self.num_of_agents:int = in_arg.num_of_agents

        self.ppm = in_arg.pixel_per_move
        if self.ppm is None:
            if map_name in MAP_CONFIG.keys():
                self.ppm = MAP_CONFIG[map_name]["pixel_per_move"]
            else:
                logging.error("Missing variable: pixel_per_move.")
                sys.exit()
        self.moves = in_arg.moves
        if self.moves is None:
            if map_name in MAP_CONFIG.keys():
                self.moves = MAP_CONFIG[map_name]["moves"]
            else:
                logging.error("Missing variable: moves.")
                sys.exit()
        self.delay:int = in_arg.delay
        if self.delay is None:
            if map_name in MAP_CONFIG.keys():
                self.delay = MAP_CONFIG[map_name]["delay"]
            else:
                logging.error("Missing variable: delay.")
                sys.exit()

        self.tile_size:int = self.ppm * self.moves
        self.width:int = -1
        self.height:int = -1
        self.env_map:List[List[int]] = []
        self.grids:List = []
        self.tasks = {}
        self.events = {}

        self.plan_paths = {}
        self.exec_paths = {}
        self.conflicts = {}
        self.agents:Dict[int,Agent] = {}
        self.makespan:int = -1
        self.cur_timestep = 0
        self.shown_path_agents = set()

        self.load_map()  # Load from files

        # Initialize the window
        self.window = tk.Tk()
        self.is_run = tk.BooleanVar()
        self.is_grid = tk.BooleanVar()
        self.show_ag_idx = tk.BooleanVar()
        self.show_task_idx = tk.BooleanVar()
        self.show_static = tk.BooleanVar()
        self.show_all_conf_ag = tk.BooleanVar()

        self.is_run.set(False)
        self.is_grid.set(in_arg.show_grid)
        self.show_ag_idx.set(in_arg.show_ag_idx)
        self.show_task_idx.set(in_arg.show_task_idx)
        self.show_static.set(in_arg.show_static)
        self.show_all_conf_ag.set(in_arg.show_conf_ag)

        # Show MAPF instance
        # Use width and height for scaling
        self.canvas = tk.Canvas(self.window,
                                width=(self.width+1) * self.tile_size,
                                height=(self.height+1) * self.tile_size,
                                bg="white")
        self.canvas.grid(row=0, column=0,sticky="nsew")
        self.canvas.configure(scrollregion = self.canvas.bbox("all"))

        # Render instance on canvas
        self.load_plan()  # Load the results
        self.render_env()
        self.render_agents()

        # This is what enables using the mouse:
        self.canvas.bind("<ButtonPress-1>", self.__move_from)
        self.canvas.bind("<B1-Motion>", self.__move_to)
        #linux scroll
        self.canvas.bind("<Button-4>", self.__wheel)
        self.canvas.bind("<Button-5>", self.__wheel)
        #windows scroll
        self.canvas.bind("<MouseWheel>",self.__wheel)

        self.canvas.bind("<Button-3>", self.show_ag_plan)

        # Generate the GUI pannel
        print("Rendering the pannel... ", end="")
        ui_text_size:int = 12
        self.frame = tk.Frame(self.window)
        self.frame.grid(row=0, column=1,sticky="nsew")
        row_idx = 0

        self.timestep_label = tk.Label(self.frame,
                                       text = f"Timestep: {self.cur_timestep:03d}",
                                       font=("Arial", ui_text_size + 10))
        self.timestep_label.grid(row=row_idx, column=0, columnspan=10, sticky="w")
        row_idx += 1

        # List of buttons
        self.run_button = tk.Button(self.frame, text="Play",
                                    font=("Arial",ui_text_size),
                                    command=self.move_agents)
        self.run_button.grid(row=row_idx, column=0, sticky="nsew")
        self.pause_button = tk.Button(self.frame, text="Pause",
                                      font=("Arial",ui_text_size),
                                      command=self.pause_agents)
        self.pause_button.grid(row=row_idx, column=1, sticky="nsew")
        self.resume_zoom_button = tk.Button(self.frame, text="Fullsize",
                                            font=("Arial",ui_text_size),
                                            command=self.resume_zoom)
        self.resume_zoom_button.grid(row=row_idx, column=2, columnspan=2, sticky="nsew")
        row_idx += 1

        self.next_button = tk.Button(self.frame, text="Next",
                                     font=("Arial",ui_text_size),
                                     command=self.move_agents_per_timestep)
        self.next_button.grid(row=row_idx, column=0, sticky="nsew")
        self.prev_button = tk.Button(self.frame, text="Prev",
                                     font=("Arial",ui_text_size),
                                     command=self.back_agents_per_timestep)
        self.prev_button.grid(row=row_idx, column=1, sticky="nsew")
        self.restart_button = tk.Button(self.frame, text="Reset",
                                        font=("Arial",ui_text_size),
                                        command=self.restart_timestep)
        self.restart_button.grid(row=row_idx, column=2, columnspan=2, sticky="nsew")
        row_idx += 1

        # List of checkboxes
        self.grid_button = tk.Checkbutton(self.frame, text="Show grids",
                                          font=("Arial",ui_text_size),
                                          variable=self.is_grid,
                                          onvalue=True, offvalue=False,
                                          command=self.show_grid)
        self.grid_button.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        row_idx += 1

        self.id_button = tk.Checkbutton(self.frame, text="Show agent indices",
                                        font=("Arial",ui_text_size),
                                        variable=self.show_ag_idx, onvalue=True, offvalue=False,
                                        command=self.show_agent_index)
        self.id_button.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        row_idx += 1

        self.id_button2 = tk.Checkbutton(self.frame, text="Show task indices",
                                         font=("Arial",ui_text_size),
                                         variable=self.show_task_idx, onvalue=True, offvalue=False,
                                         command=self.show_task_index)
        self.id_button2.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        row_idx += 1

        self.static_button = tk.Checkbutton(self.frame, text="Show start locations",
                                            font=("Arial",ui_text_size),
                                            variable=self.show_static, onvalue=True, offvalue=False,
                                            command=self.show_static_loc)
        self.static_button.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        row_idx += 1

        self.show_all_conf_ag_button = tk.Checkbutton(self.frame, text="Show colliding agnets",
                                                      font=("Arial",ui_text_size),
                                                      variable=self.show_all_conf_ag,
                                                      onvalue=True, offvalue=False,
                                                      command=self.mark_conf_agents)
        self.show_all_conf_ag_button.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        row_idx += 1

        task_label = tk.Label(self.frame, text = "Shown tasks", font = ("Arial", ui_text_size))
        task_label.grid(row=row_idx, column=0, columnspan=1, sticky="w")
        self.task_shown = ttk.Combobox(self.frame, width=8, state="readonly",
                                       values=["all", "unassigned", "assigned", "finished", "none"])
        self.task_shown.current(4)
        self.task_shown.bind('<<ComboboxSelected>>', self.show_tasks_by_click)
        self.task_shown.grid(row=row_idx, column=1, sticky="w")
        row_idx += 1

        tmp_label = tk.Label(self.frame, text="Start timestep", font=("Arial",ui_text_size))
        tmp_label.grid(row=row_idx, column=0, columnspan=1, sticky="w")
        self.new_time = tk.IntVar()
        self.start_time_entry = tk.Entry(self.frame, width=5, textvariable=self.new_time,
                                         font=("Arial",ui_text_size),
                                         validatecommand=self.update_curtime)
        self.start_time_entry.grid(row=row_idx, column=1, sticky="w")
        self.update_button = tk.Button(self.frame, text="Go", font=("Arial",ui_text_size),
                                       command=self.update_curtime)
        self.update_button.grid(row=row_idx, column=2, sticky="w")
        row_idx += 1

        # tmp_label1 = tk.Label(self.frame, text="Current mode", font=("Arial",ui_text_size))
        # tmp_label1.grid(row=row_idx, column=0, columnspan=1, sticky="w")
        # self.is_move_plan = tk.BooleanVar()
        # self.is_move_plan.set(False)
        # self.is_move_plan_button = tk.Button(self.frame, text="Exec",
        #                                      font=("Arial",ui_text_size),
        #                                      command=self.update_is_move_plan)
        # self.is_move_plan_button.grid(row=row_idx, column=1, sticky="w")
        # row_idx += 1

        tmp_label2 = tk.Label(self.frame, text="List of errors", font=("Arial",ui_text_size))
        tmp_label2.grid(row=row_idx, column=0, columnspan=3, sticky="w")
        row_idx += 1

        self.shown_conflicts:Dict[str, List[List,bool]] = {}
        self.conflict_listbox = tk.Listbox(self.frame,
                                           width=30,
                                           height=12,
                                           font=("Arial",ui_text_size),
                                           selectmode=tk.EXTENDED)
        conf_id = 0
        for _timestep_ in sorted(self.conflicts.keys(), reverse=True):
            for _conf_ in self.conflicts[_timestep_]:
                agent1 = _conf_[0]
                agent2 = _conf_[1]
                if agent1 > (self.num_of_agents-1) or agent2 > (self.num_of_agents-1):
                    continue
                timestep = _conf_[2]
                conf_str = str()
                if agent1 != -1:
                    conf_str += "a" + str(agent1)
                if agent2 != -1:
                    conf_str += ", a" + str(agent2)
                if _conf_[-1] == "vertex conflict":
                    _loc = "("+ str(self.agents[agent1].plan_path[timestep][0]) + "," +\
                        str(self.agents[agent1].plan_path[timestep][1]) +")"
                    conf_str += ", v: " + _loc
                elif _conf_[-1] == "edge conflict":
                    _loc1 = "(" + str(self.agents[agent1].plan_path[timestep-1][0]) + "," +\
                        str(self.agents[agent1].plan_path[timestep-1][1]) + ")"
                    _loc2 = "(" + str(self.agents[agent1].plan_path[timestep-1][0]) + "," +\
                        str(self.agents[agent1].plan_path[timestep-1][1]) + ")"
                    conf_str += ", e: " + _loc1 + "->" + _loc2
                elif _conf_[-1] == 'incorrect vector size':
                    conf_str += 'Planner timeout'
                else:
                    conf_str += _conf_[-1]
                conf_str += ", t: " + str(timestep)

                self.conflict_listbox.insert(conf_id, conf_str)
                self.shown_conflicts[conf_str] = [_conf_, False]
        self.conflict_listbox.grid(row=row_idx, column=0, columnspan=5, sticky="w")
        self.conflict_listbox.bind('<<ListboxSelect>>', self.select_conflict)
        self.conflict_listbox.bind('<Double-1>', self.move_to_conflict)

        scrollbar = tk.Scrollbar(self.frame, orient="vertical")
        self.conflict_listbox.config(yscrollcommand = scrollbar.set)
        scrollbar.config(command=self.conflict_listbox.yview)
        scrollbar.grid(row=row_idx, column=5, sticky="w")
        row_idx += 1

        # Show events
        tmp_label3 = tk.Label(self.frame, text="List of events", font=("Arial",ui_text_size))
        tmp_label3.grid(row=row_idx, column=0, columnspan=3, sticky="w")
        row_idx += 1

        self.shown_events:Dict[str, List[List,bool]] = {}
        self.event_listbox = tk.Listbox(self.frame,
                                        width=30,
                                        height=12,
                                        font=("Arial",ui_text_size),
                                        selectmode=tk.EXTENDED)
        eve_id = 0
        for _timestep_ in sorted(self.events.keys(), reverse=True):
            for _tid_ in sorted(self.events[_timestep_].keys(), reverse=True):
                for _eve_ in self.events[_timestep_][_tid_]["assigned"]:
                    cur_task = self.tasks[_eve_[0]]
                    eve_str = "task " + str(cur_task.idx) + " assigned to a" +\
                        str(cur_task.assign["agent"]) + " at t: " + str(cur_task.assign["timestep"])
                    self.event_listbox.insert(eve_id, eve_str)
                    self.shown_events[eve_str] = [_eve_, False]
                for _eve_ in self.events[_timestep_][_tid_]["finished"]:
                    cur_task = self.tasks[_eve_[0]]
                    eve_str = "task " + str(cur_task.idx) + " is done by a" +\
                        str(cur_task.finish["agent"]) + " at t: " + str(cur_task.finish["timestep"])
                    self.event_listbox.insert(eve_id, eve_str)
                    self.shown_events[eve_str] = [_eve_, False]

        self.event_listbox.grid(row=row_idx, column=0, columnspan=5, sticky="w")
        self.event_listbox.bind('<Double-1>', self.move_to_event)

        scrollbar = tk.Scrollbar(self.frame, orient="vertical")
        self.event_listbox.config(yscrollcommand = scrollbar.set)
        scrollbar.config(command=self.event_listbox.yview)
        scrollbar.grid(row=row_idx, column=5, sticky="w")
        row_idx += 1
        print("Done!")

        self.show_static_loc()
        self.show_agent_index()
        self.show_tasks()
        self.mark_conf_agents()
        self.resume_zoom()

        self.frame.update()  # Adjust window size
        # Use width and height for scaling
        wd_width = str((self.width+1) * self.tile_size + 300)
        wd_height = str(max((self.height+1) * self.tile_size, self.frame.winfo_height()) + 5)
        self.window.geometry(wd_width + "x" + wd_height)
        self.window.title("PlanViz")
        print("=====            DONE            =====")


    def change_ag_color(self, ag_idx:int, color:str) -> None:
        self.canvas.itemconfig(self.agents[ag_idx].agent_obj.obj, fill=color)
        self.agents[ag_idx].agent_obj.color = color


    def select_conflict(self, event):
        selected_indices = event.widget.curselection()  # get all selected indices

        for _conf_ in self.shown_conflicts.values():
            _conf_[1] = False
            if _conf_[0][0] != -1:
                self.change_ag_color(_conf_[0][0], "deepskyblue")
            if _conf_[0][1] != -1:
                self.change_ag_color(_conf_[0][1], "deepskyblue")
        for _sid_ in selected_indices:
            _conf_ = self.shown_conflicts[self.conflict_listbox.get(_sid_)]
            self.shown_conflicts[self.conflict_listbox.get(_sid_)][1] = True
            if _conf_[0][0] != -1:
                self.change_ag_color(_conf_[0][0], "red")
            if _conf_[0][1] != -1:
                self.change_ag_color(_conf_[0][1], "red")


    def restart_timestep(self):
        self.new_time.set(0)
        self.update_curtime()


    def move_to_conflict(self, event):
        if self.is_run.get() is True:
            return

        for _conf_ in self.shown_conflicts.values():
            if _conf_[0][0] != -1:
                self.change_ag_color(_conf_[0][0], "deepskyblue")
            if _conf_[0][1] != -1:
                self.change_ag_color(_conf_[0][1], "deepskyblue")
            _conf_[1] = False
        _sid_ = event.widget.curselection()[0]  # get all selected indices
        _conf_ = self.shown_conflicts[self.conflict_listbox.get(_sid_)]
        if _conf_[0][0] != -1:
            self.change_ag_color(_conf_[0][0], "red")
        if _conf_[0][1] != -1:
            self.change_ag_color(_conf_[0][1], "red")
        self.shown_conflicts[self.conflict_listbox.get(_sid_)][1] = True
        self.new_time.set(int(_conf_[0][2])-1)
        self.update_curtime()

        for (_, _agent_) in self.agents.items():
            _agent_.path = _agent_.plan_path
        self.move_agents_per_timestep()
        time.sleep(1.5)

        for (_, _agent_) in self.agents.items():
            _agent_.path = _agent_.exec_path
        self.new_time.set(int(_conf_[0][2])-1)
        self.update_curtime()


    def move_to_event(self, event):
        if self.is_run.get() is True:
            return

        for _eve_ in self.shown_events.values():
            _eve_[1] = False
        _sid_ = event.widget.curselection()[0]  # get all selected indices
        _eve_ = self.shown_events[self.event_listbox.get(_sid_)]
        self.shown_events[self.event_listbox.get(_sid_)][1] = True
        new_t = max(int(_eve_[0][1])-1, 0)
        self.new_time.set(new_t)
        self.update_curtime()


    def __move_from(self, event):
        """ Remember previous coordinates for scrolling with the mouse """
        self.canvas.scan_mark(event.x, event.y)

    def __move_to(self, event):
        """ Drag (move) canvas to the new position """
        self.canvas.scan_dragto(event.x, event.y, gain=1)


    def __wheel(self, event):
        """ Zoom with mouse wheel """
        scale = 1.0
        # Respond to Linux (event.num) or Windows (event.delta) wheel event
        if event.num == 5 or event.delta == -120:  # scroll down, smaller
            if round(min(self.width, self.height) * self.tile_size) < 30:
                return  # image is less than 30 pixels
            scale /= 1.10
            self.tile_size /= 1.10
        if event.num == 4 or event.delta == 120:  # scroll up, bigger
            scale *= 1.10
            self.tile_size *= 1.10
        self.canvas.scale("all", 0, 0, scale, scale)  # rescale all objects
        for child_widget in self.canvas.find_withtag("text"):
            self.canvas.itemconfigure(child_widget,
                                      font=("Arial", int(self.tile_size // 2)))
        self.canvas.configure(scrollregion = self.canvas.bbox("all"))


    def resume_zoom(self):
        __scale = self.ppm * self.moves / self.tile_size
        self.canvas.scale("all", 0, 0, __scale, __scale)
        self.tile_size = self.ppm * self.moves
        for child_widget in self.canvas.find_withtag("text"):
            self.canvas.itemconfigure(child_widget, font=("Arial", int(self.tile_size // 2)))
        self.canvas.configure(scrollregion = self.canvas.bbox("all"))
        self.canvas.update()


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
        _line_state_ = "normal" if self.is_grid.get() is True else "hidden"
        for rid in range(self.height):  # Render horizontal lines
            _line_ = self.canvas.create_line(0, rid * self.tile_size,
                                             self.width * self.tile_size, rid * self.tile_size,
                                             tags="grid",
                                             state= _line_state_,
                                             fill="grey")
            self.grids.append(_line_)
        for cid in range(self.width):  # Render vertical lines
            _line_ = self.canvas.create_line(cid * self.tile_size, 0,
                                             cid * self.tile_size, self.height * self.tile_size,
                                             tags="grid",
                                             state= _line_state_,
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


    @staticmethod
    def get_dir_loc(_loc_:Tuple[int]):
        dir_loc = [0.0, 0.0, 0.0, 0.0]
        if _loc_[2] == 0:  # Right
            dir_loc[1] = _loc_[0] + 0.5 - DIR_DIAMETER
            dir_loc[0] = _loc_[1] + 1 - DIR_OFFSET - DIR_DIAMETER*2
            dir_loc[3] = _loc_[0] + 0.5 + DIR_DIAMETER
            dir_loc[2] = _loc_[1] + 1 - DIR_OFFSET
        elif _loc_[2] == 1:  # Up
            dir_loc[1] = _loc_[0] + DIR_OFFSET
            dir_loc[0] = _loc_[1] + 0.5 - DIR_DIAMETER
            dir_loc[3] = _loc_[0] + DIR_OFFSET + DIR_DIAMETER*2
            dir_loc[2] = _loc_[1] + 0.5 + DIR_DIAMETER
        elif _loc_[2] == 2:  # Left
            dir_loc[1] = _loc_[0] + 0.5 - DIR_DIAMETER
            dir_loc[0] = _loc_[1] + DIR_OFFSET
            dir_loc[3] = _loc_[0] + 0.5 + DIR_DIAMETER
            dir_loc[2] = _loc_[1] + DIR_OFFSET + DIR_DIAMETER*2
        elif _loc_[2] == 3:  # Down
            dir_loc[1] = _loc_[0] + 1 - DIR_OFFSET - DIR_DIAMETER*2
            dir_loc[0] = _loc_[1] + 0.5 - DIR_DIAMETER
            dir_loc[3] = _loc_[0] + 1 - DIR_OFFSET
            dir_loc[2] = _loc_[1] + 0.5 + DIR_DIAMETER
        return dir_loc


    def render_agents(self):
        print("Rendering the agents... ", end="")
        # Separate the render of static locations and agents so that agents can overlap
        start_objs = []
        plan_path_objs = []

        for _ag_ in range(self.num_of_agents):
            start = self.render_obj(_ag_, self.plan_paths[_ag_][0],"oval","yellowgreen","disable")
            start_objs.append(start)

            ag_path = []
            for _pid_ in range(len(self.plan_paths[_ag_])):
                _p_loc_ = (self.plan_paths[_ag_][_pid_][0], self.plan_paths[_ag_][_pid_][1])
                _p_obj = None
                if _pid_ > 0 and _p_loc_ == (self.plan_paths[_ag_][_pid_-1][0],
                                             self.plan_paths[_ag_][_pid_-1][1]):
                    _p_obj = self.render_obj(_ag_, _p_loc_, "rectangle", "purple", "disable", 0.25)
                else:  # non=wait action, smaller rectangle
                    _p_obj = self.render_obj(_ag_, _p_loc_, "rectangle", "purple", "disable", 0.4)
                self.canvas.itemconfigure(_p_obj.obj, state="hidden")
                self.canvas.delete(_p_obj.text)
                ag_path.append(_p_obj)
            plan_path_objs.append(ag_path)

        if len(self.exec_paths) == 0:
            raise ValueError("Missing actual paths!")
        shown_paths = self.exec_paths

        for _ag_ in range(self.num_of_agents):
            agent_obj = self.render_obj(_ag_, shown_paths[_ag_][0], "oval",
                                        "deepskyblue", "hidden", 0.05, str(_ag_))
            dir_loc = self.get_dir_loc(shown_paths[_ag_][0])
            dir_obj = self.canvas.create_oval(dir_loc[0] * self.tile_size,
                                              dir_loc[1] * self.tile_size,
                                              dir_loc[2] * self.tile_size,
                                              dir_loc[3] * self.tile_size,
                                              fill="navy",
                                              tag="dir",
                                              state="hidden",
                                              outline="")

            agent = Agent(_ag_, agent_obj, start_objs[_ag_], self.plan_paths[_ag_],
                          plan_path_objs[_ag_], self.exec_paths[_ag_], dir_obj)
            self.agents[_ag_] = agent
        print("Done!")


    def show_ag_plan(self, event):
        item = self.canvas.find_closest(event.x, event.y)[0]
        tags:set(str) = self.canvas.gettags(item)
        ag_idx = -1
        for _tt_ in tags:
            if _tt_.isnumeric():
                ag_idx = int(_tt_)  # get the id of the agent
                break
        if ag_idx == -1:
            return

        if ag_idx in self.shown_path_agents:
            self.shown_path_agents.remove(ag_idx)
            for _p_ in self.agents[ag_idx].plan_path_objs:
                self.canvas.itemconfigure(_p_.obj, state="hidden")
        else:
            self.shown_path_agents.add(ag_idx)
            for _pid_ in range(self.cur_timestep+1, len(self.agents[ag_idx].plan_path_objs)):
                self.canvas.itemconfigure(self.agents[ag_idx].plan_path_objs[_pid_].obj,
                                          state="disable")


    def mark_conf_agents(self) -> None:
        self.conflict_listbox.select_clear(0, self.conflict_listbox.size())
        _color_ = "red" if self.show_all_conf_ag.get() else "deepskyblue"
        for _conf_ in self.shown_conflicts.values():
            if _conf_[0][0] != -1:
                self.change_ag_color(_conf_[0][0], _color_)
            if _conf_[0][1] != -1:
                self.change_ag_color(_conf_[0][1], _color_)
            _conf_[1] = False


    def show_grid(self) -> None:
        if self.is_grid.get() is True:
            for _line_ in self.grids:
                self.canvas.itemconfig(_line_, state="normal")
        else:
            for _line_ in self.grids:
                self.canvas.itemconfig(_line_, state="hidden")


    def show_agent_index(self) -> None:
        _state_ = "disable" if self.show_ag_idx.get() is True else "hidden"
        _ts_ = "disable" if (self.show_ag_idx.get() is True and\
            self.show_static.get() is True) else "hidden"
        for (_, _agent_) in self.agents.items():
            self.canvas.itemconfig(_agent_.agent_obj.text, state=_state_)
            self.canvas.itemconfig(_agent_.start_obj.text, state=_ts_)


    def show_task_index(self) -> None:
        for (_, _task_) in self.tasks.items():
            if self.task_shown.get() in [_task_.state, "all"] and self.show_task_idx.get():
                self.canvas.itemconfig(_task_.task_obj.text, state="disable")
            else:
                self.canvas.itemconfig(_task_.task_obj.text, state="hidden")


    def show_tasks(self) -> None:
        for (_, _task_) in self.tasks.items():
            if self.task_shown.get() in [ _task_.state, "all"]:
                self.canvas.itemconfig(_task_.task_obj.obj, state="disable")
            else:
                self.canvas.itemconfig(_task_.task_obj.obj, state="hidden")
        self.show_task_index()


    def show_tasks_by_click(self, event) -> None:
        self.show_tasks()


    def show_static_loc(self) -> None:
        _os_ = "disable" if self.show_static.get() is True else "hidden"
        _ts_ = "disable" if (self.show_ag_idx.get() is True and\
            self.show_static.get() is True) else "hidden"
        for (_, _agent_) in self.agents.items():
            self.canvas.itemconfig(_agent_.start_obj.obj, state=_os_)
            self.canvas.itemconfig(_agent_.start_obj.text, state=_ts_)


    def load_map(self, map_file:str = None) -> None:
        if map_file is None:
            map_file = self.map_file
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


    def load_plan(self):
        fin = open(file=self.plan_file, mode="r", encoding="UTF-8")
        data = json.load(fin)

        if self.num_of_agents == np.inf:
            self.num_of_agents = data["teamSize"]

        print("Loading paths from "+str(self.plan_file), end="... ")
        for ag_idx in range(self.num_of_agents):
            self.plan_paths[ag_idx] = []
            self.exec_paths[ag_idx] = []
            start = data["start"][ag_idx]
            # start=literal_eval(start)
            # print(start,start[0],start[1],start[2])
            start = (int(start[0]), int(start[1]), DIRECTION[start[2]])
            self.plan_paths[ag_idx].append(start)
            self.exec_paths[ag_idx].append(start)

            if "actualPaths" not in data.keys():
                raise KeyError("Missing actualPaths.")
            tmp_str = data["actualPaths"][ag_idx].split(",")
            for _motion_ in tmp_str:
                next_state = self.state_transition(self.exec_paths[ag_idx][-1], _motion_)
                self.exec_paths[ag_idx].append(next_state)
            if self.makespan < max(len(self.exec_paths[ag_idx])-1, 0):
                self.makespan = max(len(self.exec_paths[ag_idx])-1, 0)

            if "plannerPaths" not in data.keys():
                raise KeyError("Missing plannerPaths.")
            tmp_str = data["plannerPaths"][ag_idx].split(",")
            for _timestep_, _motion_ in enumerate(tmp_str):
                next_state = self.state_transition(self.exec_paths[ag_idx][_timestep_], _motion_)
                self.plan_paths[ag_idx].append(next_state)
            if self.makespan < max(len(self.plan_paths[ag_idx])-1, 0):
                self.makespan = max(len(self.plan_paths[ag_idx])-1, 0)

        print("Done!")

        print("Loading errors from "+str(self.plan_file), end="... ")
        if "errors" in data:
            for err in data["errors"]:
                timestep = err[2]
                if timestep not in self.conflicts.keys():  # Sort errors according to the timestep
                    self.conflicts[timestep] = []
                self.conflicts[timestep].append(err)
        print("Done!")

        print("Loading tasks from "+str(self.plan_file), end="... ")
        if "tasks" in data.keys() and data["tasks"]:
            for _task_ in data["tasks"]:
                _tid_ = _task_[0]
                _tloc_ = (_task_[1], _task_[2])
                _tobj_ = self.render_obj(_tid_, _tloc_, "rectangle", TASK_COLORS["unassigned"])
                new_task = Task(_tid_, _tloc_, _tobj_)
                self.tasks[_tid_] = new_task
        print("Done!")

        print("Loading events from "+str(self.plan_file), end="... ")
        if "events" in data.keys() and data["events"]:
            for _ag_ in range(self.num_of_agents):
                for _eve_ in data["events"][_ag_]:
                    _tid_ = _eve_[0]
                    _timestep_ = _eve_[1]

                    if  _timestep_ not in self.events.keys():
                        self.events[_timestep_] = {}
                    if _tid_ not in self.events[_timestep_].keys():
                        self.events[_timestep_][_tid_] = {"assigned":[], "finished":[]}

                    if _eve_[2] == "assigned":
                        self.tasks[_tid_].assign["agent"] = _ag_
                        self.tasks[_tid_].assign["timestep"] = _timestep_
                        if _timestep_ == 0:  # timestep at 0
                            self.tasks[_tid_].state = "assigned"
                            self.canvas.itemconfig(self.tasks[_tid_].task_obj.obj,
                                                   fill=TASK_COLORS["assigned"])
                        self.events[_timestep_][_tid_]["assigned"].append(_eve_)

                    elif _eve_[2] == "finished":
                        self.tasks[_tid_].finish["agent"] = _ag_
                        self.tasks[_tid_].finish["timestep"] = _timestep_
                        if _timestep_ == 0:  # timestep at 0
                            self.tasks[_tid_].state = "finished"
                            self.canvas.itemconfig(self.tasks[_tid_].task_obj.obj,
                                                   fill=TASK_COLORS["finished"])
                        self.events[_timestep_][_tid_]["finished"].append(_eve_)

        print("Done!")


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
        elif motion == "W" or motion == "T":
            return cur_state
        else:
            logging.error("Invalid motion")
            sys.exit()


    def get_rotation(self, cur_dir:int, next_dir:int):
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


    def move_agents_per_timestep(self) -> None:
        self.next_button.config(state="disable")
        _rad_ = ((1 - 2*DIR_OFFSET) - 0.1*2) * self.tile_size/2

        for _m_ in range(self.moves):
            if _m_ == self.moves // 2:
                self.timestep_label.config(text = f"Timestep: {self.cur_timestep+1:03d}")

            for (_, agent) in self.agents.items():
                next_timestep = min(self.cur_timestep+1, len(agent.path)-1)
                cur_angle = get_angle(agent.agent_obj.loc[2])
                direction = (agent.path[next_timestep][1] - agent.agent_obj.loc[1],
                             agent.path[next_timestep][0] - agent.agent_obj.loc[0])
                cur_move = (direction[0] * (self.tile_size / self.moves),
                            direction[1] * (self.tile_size / self.moves))
                cur_rotation = self.get_rotation(agent.agent_obj.loc[2],
                                                 agent.path[next_timestep][2])
                next_ang = cur_rotation*(math.pi/2)/(self.moves)

                # Move agent
                _cos = math.cos(cur_angle + next_ang * (_m_+1)) - math.cos(cur_angle+next_ang*_m_)
                _sin = -1 * (math.sin(cur_angle+ next_ang*(_m_+1))-math.sin(cur_angle+next_ang*_m_))
                self.canvas.move(agent.agent_obj.obj, cur_move[0], cur_move[1])
                self.canvas.move(agent.agent_obj.text, cur_move[0], cur_move[1])
                self.canvas.move(agent.dir_obj, cur_move[0], cur_move[1])
                self.canvas.move(agent.dir_obj,
                                 _rad_ * _cos,
                                 _rad_ * _sin)

            self.canvas.update()
            time.sleep(self.delay)

        for (_, _task_) in self.tasks.items():
            if self.cur_timestep+1 >= _task_.finish["timestep"]:
                _task_.state = "finished"
            elif self.cur_timestep+1 >= _task_.assign["timestep"]:
                _task_.state = "assigned"
            else:
                _task_.state = "unassigned"
            self.canvas.itemconfig(_task_.task_obj.obj, fill=TASK_COLORS[_task_.state])
        self.show_tasks()

        for (_, agent) in self.agents.items():
            next_timestep = min(self.cur_timestep+1, len(agent.path)-1)
            agent.agent_obj.loc = (agent.path[next_timestep][0],
                                   agent.path[next_timestep][1],
                                   agent.path[next_timestep][2])
        self.cur_timestep += 1
        self.next_button.config(state="normal")


    def back_agents_per_timestep(self) -> None:
        if self.cur_timestep == 0:
            return

        self.prev_button.config(state="disable")
        _rad_ = ((1 - 2*DIR_OFFSET) - 0.1*2) * self.tile_size/2

        prev_timestep = max(self.cur_timestep-1, 0)
        prev_loc:Dict[int, Tuple[int, int]] = {}
        for (ag_idx, agent) in self.agents.items():
            if prev_timestep > len(agent.path)-1:
                prev_loc[ag_idx] = (agent.path[-1][0], agent.path[-1][1], agent.path[-1][2])
            else:
                prev_loc[ag_idx] = (agent.path[prev_timestep][0],
                                    agent.path[prev_timestep][1],
                                    agent.path[prev_timestep][2])

        for _m_ in range(self.moves):
            if _m_ == self.moves // 2:
                self.timestep_label.config(text = f"Timestep: {prev_timestep:03d}")
            for (ag_idx, agent) in self.agents.items():
                cur_angle = get_angle(agent.agent_obj.loc[2])
                direction = (prev_loc[ag_idx][1] - agent.agent_obj.loc[1],
                             prev_loc[ag_idx][0] - agent.agent_obj.loc[0])
                cur_move = (direction[0] * (self.tile_size / self.moves),
                            direction[1] * (self.tile_size / self.moves))
                cur_rotation = self.get_rotation(agent.agent_obj.loc[2],
                                                    prev_loc[ag_idx][2])
                next_ang = cur_rotation*(math.pi/2)/(self.moves)

                # Move agent
                _cos = math.cos(cur_angle+next_ang*(_m_+1)) - math.cos(cur_angle + next_ang*_m_)
                _sin = -1*(math.sin(cur_angle+next_ang*(_m_+1))-math.sin(cur_angle + next_ang*_m_))
                self.canvas.move(agent.agent_obj.obj, cur_move[0], cur_move[1])
                self.canvas.move(agent.agent_obj.text, cur_move[0], cur_move[1])
                self.canvas.move(agent.dir_obj, cur_move[0], cur_move[1])
                self.canvas.move(agent.dir_obj,
                                 _rad_*_cos,
                                 _rad_*_sin)

            self.canvas.update()
            time.sleep(self.delay)

        for (_, _task_) in self.tasks.items():
            if prev_timestep >= _task_.finish["timestep"]:
                _task_.state = "finished"
            elif prev_timestep >= _task_.assign["timestep"]:
                _task_.state = "assigned"
            else:
                _task_.state = "unassigned"
            self.canvas.itemconfig(_task_.task_obj.obj, fill=TASK_COLORS[_task_.state])
        self.show_tasks()

        self.cur_timestep = prev_timestep
        for (ag_idx, agent) in self.agents.items():
            agent.agent_obj.loc = prev_loc[ag_idx]

        self.prev_button.config(state="normal")


    def move_agents(self) -> None:
        """Move agents from cur_timstep to cur_timestep+1 and increase the cur_timestep by 1
        """
        self.run_button.config(state="disable")
        self.pause_button.config(state="normal")
        self.next_button.config(state="disable")
        self.prev_button.config(state="disable")
        self.update_button.config(state="disable")
        self.restart_button.config(state="disable")

        self.is_run.set(True)
        while self.cur_timestep < self.makespan:
            if self.is_run.get() is True:
                self.move_agents_per_timestep()
                time.sleep(self.delay * 2)
            else:
                break

        self.run_button.config(state="normal")
        self.pause_button.config(state="normal")
        self.next_button.config(state="normal")
        self.prev_button.config(state="normal")
        self.update_button.config(state="normal")
        self.restart_button.config(state="normal")


    def pause_agents(self) -> None:
        self.is_run.set(False)
        self.pause_button.config(state="disable")
        self.run_button.config(state="normal")
        self.next_button.config(state="normal")
        self.prev_button.config(state="normal")
        self.canvas.after(200, lambda: self.pause_button.config(state="normal"))


    def update_curtime(self) -> None:
        self.cur_timestep = self.new_time.get()
        self.timestep_label.config(text = f"Timestep: {self.cur_timestep:03d}")

        for (_, _task_) in self.tasks.items():
            if self.cur_timestep >= _task_.finish["timestep"]:
                _task_.state = "finished"
            elif self.cur_timestep >= _task_.assign["timestep"]:
                _task_.state = "assigned"
            else:
                _task_.state = "unassigned"
            self.canvas.itemconfig(_task_.task_obj.obj, fill=TASK_COLORS[_task_.state])
        self.show_tasks()

        for (_idx_, _agent_) in self.agents.items():
            _color_ = _agent_.agent_obj.color
            _time_ = min(self.cur_timestep, len(_agent_.path)-1)
            self.canvas.delete(_agent_.agent_obj.obj)
            self.canvas.delete(_agent_.agent_obj.text)
            self.canvas.delete(_agent_.dir_obj)
            _agent_.agent_obj = self.render_obj(_idx_, _agent_.path[_time_], "oval", _color_,
                                                "normal", 0.05, str(_idx_))

            dir_loc = self.get_dir_loc(_agent_.path[_time_])
            _agent_.dir_obj = self.canvas.create_oval(dir_loc[0] * self.tile_size,
                                                      dir_loc[1] * self.tile_size,
                                                      dir_loc[2] * self.tile_size,
                                                      dir_loc[3] * self.tile_size,
                                                      fill="navy",
                                                      tag="dir",
                                                      state="disable",
                                                      outline="")
        self.show_agent_index()


    # def update_is_move_plan(self) -> None:
    #     if self.is_run.get() is True:
    #         return
    #     if self.is_move_plan.get() is False:
    #         self.is_move_plan.set(True)
    #         self.is_move_plan_button.configure(text="Plan")
    #     else:
    #         self.is_move_plan.set(False)
    #         self.is_move_plan_button.configure(text="Exec")

    #     for (_, _agent_) in self.agents.items():
    #         if self.is_move_plan.get() is True:
    #             _agent_.path = _agent_.plan_path
    #         else:
    #             _agent_.path = _agent_.exec_path
    #     self.update_curtime()


def main() -> None:
    """The main function of the visualizer.
    """
    parser = argparse.ArgumentParser(description='Plan visualizer for a MAPF instance')
    parser.add_argument('--map', type=str, help="Path to the map file")
    parser.add_argument('--plan', type=str, help="Path to the planned path file")
    parser.add_argument('--n', type=int, default=np.inf, dest="num_of_agents",
                        help="Number of agents")
    parser.add_argument('--ppm', type=int, dest="pixel_per_move", help="Number of pixels per move")
    parser.add_argument('--mv', type=int, dest="moves", help="Number of moves per action")
    parser.add_argument('--delay', type=float, help="Wait time between timesteps")
    parser.add_argument('--grid', action='store_true', dest="show_grid",
                        help="Show grid on the environment or not")
    parser.add_argument('--aid', action='store_true', dest="show_ag_idx",
                        help="Show agent indices or not")
    parser.add_argument('--tid', action='store_true', dest="show_task_idx",
                        help="Show task indices or not")
    parser.add_argument('--static', action='store_true', dest="show_static",
                        help="Show start locations or not")
    parser.add_argument('--ca', action='store_true', dest="show_conf_ag",
                        help="Show all colliding agents")
    args = parser.parse_args()

    PlanVis(args)
    tk.mainloop()


if __name__ == "__main__":
    main()
