# -*- coding: UTF-8 -*-
""" Plan Visualizer with rotation agents
This is a script for visualizing the plan for the League of Robot Runners.
All rights reserved.
"""

import math
import re
from bisect import bisect_right
from typing import List, Tuple, Dict, Set
import tkinter as tk
from tkinter import ttk,font
import time
import platform
from PIL import Image, ImageTk
from util import (AGENT_COLORS, AgentStatus, DIR_OFFSET, TASK_COLORS, TEXT_SIZE, get_angle,
                  get_dir_loc, get_rotation)
from plan_config import PlanConfig2023, PlanConfig2024


class PlanViz2023:
    """ This is the control panel of PlanViz
    """
    def __init__(self, plan_config, _grid, _ag_idx, _task_idx, _static, _conf_ag):
        print("===== Initialize PlanViz    =====")

        # Load the yaml file or the input arguments
        self.pcf:PlanConfig2023 = plan_config
        
        # Platform-specific right-click binding
        self.pcf.canvas.bind("<Button-3>", self.show_ag_plan_by_click)

        # Ensure canvas can receive focus and mouse events

        # This is what enables using the mouse:
        self.pcf.canvas.bind("<ButtonPress-1>", self.__move_from)
        self.pcf.canvas.bind("<B1-Motion>", self.__move_to)
        # linux scroll
        self.pcf.canvas.bind("<Button-4>", self.__wheel)
        self.pcf.canvas.bind("<Button-5>", self.__wheel)
        # windows and macOS scroll
        self.pcf.canvas.bind("<MouseWheel>",self.__wheel)

        # Generate the UI panel
        print("Rendering the panel... ", end="")

        self.is_run = tk.BooleanVar()
        self.is_grid = tk.BooleanVar()
        self.show_ag_idx = tk.BooleanVar()
        self.show_task_idx = tk.BooleanVar()
        self.show_static = tk.BooleanVar()
        self.show_all_conf_ag = tk.BooleanVar()
        self.is_heat_map = tk.BooleanVar()
        self.is_highway = tk.BooleanVar()
        self.is_heuristic_map = tk.BooleanVar()
        
        self.is_run.set(False)
        self.is_grid.set(_grid)
        self.show_ag_idx.set(_ag_idx)
        self.show_task_idx.set(_task_idx)
        self.show_static.set(_static)
        self.show_all_conf_ag.set(_conf_ag)
        self.is_heat_map.set(False)
        self.is_highway.set(False)
        self.is_heuristic_map.set(False)

        gui_window = self.pcf.window
        gui_column = 1
        if (self.pcf.width+1) * self.pcf.tile_size > 0.5 * self.pcf.window.winfo_screenwidth():
            gui_window = tk.Toplevel()
            gui_window.title("UI Panel")
            gui_window.config(width=300, height=(self.pcf.height+1) * self.pcf.tile_size)
            gui_column = 0
        self.frame = tk.Frame(gui_window)
        self.frame.grid(row=0, column=gui_column,sticky="nsew")
        row_idx = 0

        self.timestep_label = tk.Label(self.frame,
                                       text = f"Timestep: {self.pcf.cur_tstep:03d}",
                                       font=("Arial", TEXT_SIZE + 10))
        self.timestep_label.grid(row=row_idx, column=0, columnspan=10, sticky="w")
        row_idx += 1

        # ---------- List of buttons ------------------------------- #
        self.run_button = tk.Button(self.frame, text="Play",
                                    font=("Arial",TEXT_SIZE),
                                    command=self.move_agents)
        self.run_button.grid(row=row_idx, column=0, sticky="nsew")
        self.pause_button = tk.Button(self.frame, text="Pause",
                                      font=("Arial",TEXT_SIZE),
                                      command=self.pause_agents)
        self.pause_button.grid(row=row_idx, column=1, sticky="nsew")
        self.resume_zoom_button = tk.Button(self.frame, text="Fullsize",
                                            font=("Arial",TEXT_SIZE),
                                            command=self.resume_zoom)
        self.resume_zoom_button.grid(row=row_idx, column=2, columnspan=2, sticky="nsew")
        row_idx += 1

        self.next_button = tk.Button(self.frame, text="Next",
                                     font=("Arial",TEXT_SIZE),
                                     command=self.move_agents_per_timestep)
        self.next_button.grid(row=row_idx, column=0, sticky="nsew")
        self.prev_button = tk.Button(self.frame, text="Prev",
                                     font=("Arial",TEXT_SIZE),
                                     command=self.back_agents_per_timestep)
        self.prev_button.grid(row=row_idx, column=1, sticky="nsew")
        self.restart_button = tk.Button(self.frame, text="Reset",
                                        font=("Arial",TEXT_SIZE),
                                        command=self.restart_timestep)
        self.restart_button.grid(row=row_idx, column=2, columnspan=2, sticky="nsew")
        row_idx += 1

        # ---------- List of checkboxes ---------------------------- #
        self.grid_button = tk.Checkbutton(self.frame, text="Show grids",
                                          font=("Arial",TEXT_SIZE),
                                          variable=self.is_grid,
                                          onvalue=True, offvalue=False,
                                          command=self.show_grid)
        self.grid_button.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        row_idx += 1

        self.id_button = tk.Checkbutton(self.frame, text="Show agent indices",
                                        font=("Arial",TEXT_SIZE),
                                        variable=self.show_ag_idx, onvalue=True, offvalue=False,
                                        command=self.show_agent_index)
        self.id_button.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        row_idx += 1

        self.id_button2 = tk.Checkbutton(self.frame, text="Show task indices",
                                         font=("Arial",TEXT_SIZE),
                                         variable=self.show_task_idx, onvalue=True, offvalue=False,
                                         command=self.show_task_index)
        self.id_button2.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        row_idx += 1

        self.static_button = tk.Checkbutton(self.frame, text="Show start locations",
                                            font=("Arial",TEXT_SIZE),
                                            variable=self.show_static, onvalue=True, offvalue=False,
                                            command=self.show_static_loc)
        self.static_button.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        row_idx += 1

        self.show_all_conf_ag_button = tk.Checkbutton(self.frame, text="Show colliding agents",
                                                      font=("Arial",TEXT_SIZE),
                                                      variable=self.show_all_conf_ag,
                                                      onvalue=True, offvalue=False,
                                                      command=self.mark_conf_agents)
        self.show_all_conf_ag_button.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        row_idx += 1

        self.heat_map_button = tk.Checkbutton(self.frame, text="Show heatmap",
                                              font=("Arial",TEXT_SIZE),
                                              variable=self.is_heat_map,
                                              onvalue=True, offvalue=False,
                                              command=self.show_heat_map)
        self.heat_map_button.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        row_idx += 1

        self.highway_button = tk.Checkbutton(self.frame, text="Show highway",
                                             font=("Arial",TEXT_SIZE),
                                             variable=self.is_highway,
                                             onvalue=True, offvalue=False,
                                             command=self.show_highway)
        self.highway_button.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        row_idx += 1

        self.heuristic_map_button = tk.Checkbutton(self.frame, text="Show heuristic",
                                                   font=("Arial",TEXT_SIZE),
                                                   variable=self.is_heuristic_map,
                                                   onvalue=True, offvalue=False,
                                                   command=self.show_heuristic_map)
        self.heuristic_map_button.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        row_idx += 1

        # ---------- Show low-level search trees ------------------- #
        tree_label = tk.Label(self.frame, text="Search trees", font=("Arial", TEXT_SIZE))
        tree_label.grid(row=row_idx, column=0, columnspan=1, sticky="w")

        tree_combobox = ["None"]
        for tree_ele in self.pcf.search_tree_grids.keys():
            tree_combobox.append(tree_ele)
        self.tree_shown = ttk.Combobox(self.frame, width=8, state="readonly",
                                       values=tree_combobox)
        self.tree_shown.current(0)
        self.tree_shown.bind("<<ComboboxSelected>>", self.show_search_tree)
        self.tree_shown.grid(row=row_idx, column=1, sticky="w")
        row_idx += 1

        # ---------- Show tasks according to their states ---------- #
        task_label = tk.Label(self.frame, text = "Shown tasks", font = ("Arial", TEXT_SIZE))
        task_label.grid(row=row_idx, column=0, columnspan=1, sticky="w")
        self.task_shown = ttk.Combobox(self.frame, width=8, state="readonly",
                                       values=["all",
                                               "unassigned",
                                               "newlyassigned",
                                               "assigned",
                                               "finished",
                                               "none"])
        self.task_shown.current(0)
        self.task_shown.bind("<<ComboboxSelected>>", self.show_tasks_by_click)
        self.task_shown.grid(row=row_idx, column=1, sticky="w")
        row_idx += 1

        # ---------- Set the starting timestep --------------------- #
        st_label = tk.Label(self.frame, text="Start timestep", font=("Arial",TEXT_SIZE))
        st_label.grid(row=row_idx, column=0, columnspan=1, sticky="w")
        self.new_time = tk.IntVar()
        self.start_time_entry = tk.Entry(self.frame, width=5, textvariable=self.new_time,
                                         font=("Arial",TEXT_SIZE))
        self.start_time_entry.grid(row=row_idx, column=1, sticky="w")
        self.update_button = tk.Button(self.frame, text="Go", font=("Arial",TEXT_SIZE),
                                       command=self.update_curtime)
        self.update_button.grid(row=row_idx, column=2, sticky="w")
        row_idx += 1

        # ---------- Show the list of errors ----------------------- #
        err_label = tk.Label(self.frame, text="List of errors", font=("Arial",TEXT_SIZE))
        err_label.grid(row=row_idx, column=0, columnspan=3, sticky="w")
        row_idx += 1

        self.shown_conflicts:Dict[str, List[List,bool]] = {}
        self.conflict_listbox = tk.Listbox(self.frame,
                                           width=30,
                                           height=9,
                                           font=("Arial",TEXT_SIZE),
                                           selectmode=tk.EXTENDED)
        conf_id = 0
        for tstep in sorted(self.pcf.conflicts.keys(), reverse=True):
            if tstep < self.pcf.start_tstep:
                continue
            if tstep > self.pcf.end_tstep:
                break

            for conf in self.pcf.conflicts[tstep]:
                agent1 = conf[0]
                agent2 = conf[1]
                if agent1 > (self.pcf.team_size-1) or agent2 > (self.pcf.team_size-1):
                    continue
                assert tstep == conf[2]
                pid = tstep - self.pcf.start_tstep
                conf_str = str()
                if agent1 != -1:
                    conf_str += "a" + str(agent1)
                if agent2 != -1:
                    conf_str += ", a" + str(agent2)
                if conf[-1] == "vertex conflict":
                    _loc = "("+ str(self.pcf.agents[agent1].plan_path[pid][0]) + "," +\
                        str(self.pcf.agents[agent1].plan_path[pid][1]) +")"
                    conf_str += ", v: " + _loc
                elif conf[-1] == "edge conflict":
                    _loc1 = "(" + str(self.pcf.agents[agent1].plan_path[pid-1][0]) + "," +\
                        str(self.pcf.agents[agent1].plan_path[pid-1][1]) + ")"
                    _loc2 = "(" + str(self.pcf.agents[agent1].plan_path[pid-1][0]) + "," +\
                        str(self.pcf.agents[agent1].plan_path[pid-1][1]) + ")"
                    conf_str += ", e: " + _loc1 + "->" + _loc2
                elif conf[-1] == "incorrect vector size":
                    conf_str += "Planner timeout"
                # elif conf[-1] == "incorrect vector size":
                    
                else:
                    conf_str += conf[-1]
                conf_str += ", t: " + str(tstep)
                self.conflict_listbox.insert(conf_id, conf_str)
                self.shown_conflicts[conf_str] = [conf, False]

        self.conflict_listbox.grid(row=row_idx, column=0, columnspan=5, sticky="w")
        self.conflict_listbox.bind("<<ListboxSelect>>", self.select_conflict)
        self.conflict_listbox.bind("<Double-1>", self.move_to_conflict)

        scrollbar = tk.Scrollbar(self.frame, orient="vertical")
        self.conflict_listbox.config(yscrollcommand = scrollbar.set)
        scrollbar.config(command=self.conflict_listbox.yview)
        scrollbar.grid(row=row_idx, column=5, sticky="w")
        row_idx += 1

        # ---------- Show the list of events ----------------------- #
        event_label = tk.Label(self.frame, text="List of events", font=("Arial",TEXT_SIZE))
        event_label.grid(row=row_idx, column=0, columnspan=3, sticky="w")
        row_idx += 1

        self.shown_events:Dict[str, Tuple[int,int,int,str]] = {}
        self.event_listbox = tk.Listbox(self.frame,
                                        width=30,
                                        height=9,
                                        font=("Arial",TEXT_SIZE),
                                        selectmode=tk.EXTENDED)
        eve_id = 0
        time_list = list(self.pcf.events["assigned"])
        time_list.extend(x for x in self.pcf.events["finished"] if x not in time_list)
        time_list = sorted(time_list, reverse=False)
        for tstep in time_list:
            if tstep in self.pcf.events["assigned"]:
                cur_events = self.pcf.events["assigned"][tstep]
                for tid in sorted(cur_events.keys(), reverse=False):
                    ag_id = cur_events[tid]
                    e_str = "task "+str(tid) + " assigned to a"+str(ag_id) + " at t:"+str(tstep)
                    self.shown_events[e_str] = (tstep, tid, ag_id, "assigned")
                    self.event_listbox.insert(eve_id, e_str)
                    eve_id += 1
            if tstep in self.pcf.events["finished"]:
                cur_events = self.pcf.events["finished"][tstep]
                for tid in sorted(cur_events.keys(), reverse=False):
                    ag_id = cur_events[tid]
                    e_str = "task "+str(tid) + "   is done by a"+str(ag_id) + " at t:"+str(tstep)
                    self.shown_events[e_str] = (tstep, tid, ag_id, "finished")
                    self.event_listbox.insert(eve_id, e_str)
                    eve_id += 1

        self.event_listbox.grid(row=row_idx, column=0, columnspan=5, sticky="w")
        self.event_listbox.bind("<Double-1>", self.move_to_event)

        scrollbar = tk.Scrollbar(self.frame, orient="vertical")
        self.event_listbox.config(yscrollcommand = scrollbar.set)
        scrollbar.config(command=self.event_listbox.yview)
        scrollbar.grid(row=row_idx, column=5, sticky="w")
        row_idx += 1
        print("Done!")

        self.show_grid()
        self.show_static_loc()
        self.show_tasks()
        self.mark_conf_agents()
        self.resume_zoom()

        self.new_time.set(self.pcf.start_tstep)
        self.update_curtime()

        self.frame.update()  # Adjust window size
        # Use width and height for scaling
        wd_width  = min((self.pcf.width+1) * self.pcf.tile_size + 2,
                        self.pcf.window.winfo_screenwidth())
        wd_height = (self.pcf.height+1) * self.pcf.tile_size + 1
        if gui_column == 1:
            wd_width += self.frame.winfo_width() + 3
            wd_height = max(wd_height, self.frame.winfo_height()) + 5
        wd_width = str(wd_width)
        wd_height = str(wd_height)
        self.pcf.window.geometry(wd_width + "x" + wd_height)
        self.pcf.window.title("PlanViz")
        print("=====          DONE         =====")


    def change_ag_color(self, ag_idx:int, color:str) -> None:
        ag_color = color
        if (self.show_all_conf_ag.get() and ag_idx in self.pcf.conflict_agents) or \
            self.pcf.canvas.itemcget(self.pcf.agents[ag_idx].agent_obj.obj, "fill") \
                == AGENT_COLORS["collide"]:
            ag_color = AGENT_COLORS["collide"]
        if ag_color != AGENT_COLORS["collide"]:
            self.pcf.agents[ag_idx].agent_obj.color = ag_color
        self.pcf.canvas.itemconfig(self.pcf.agents[ag_idx].agent_obj.obj, fill=ag_color)


    def change_task_color(self, task_id:int, color:str) -> None:
        """ Change the color of the task

        Args:
            task_id (int): the index in self.pcf.tasks
            color   (str): the color to be changed
        """
        # Change the color of the task
        if self.pcf.canvas.itemcget(self.pcf.tasks[task_id].task_obj.obj, "fill") != color:
            self.pcf.canvas.itemconfig(self.pcf.tasks[task_id].task_obj.obj, fill=color)


    def select_conflict(self, event):
        selected_indices = event.widget.curselection()  # Get all selected indices

        for conf in self.shown_conflicts.values():  # Reset all the conflicts to non-selected
            conf[1] = False
            if conf[0][0] != -1:
                self.pcf.canvas.itemconfig(self.pcf.agents[conf[0][0]].agent_obj.obj,
                                           fill=self.pcf.agents[conf[0][0]].agent_obj.color)
            if conf[0][1] != -1:
                self.pcf.canvas.itemconfig(self.pcf.agents[conf[0][1]].agent_obj.obj,
                                           fill=self.pcf.agents[conf[0][1]].agent_obj.color)

        for _sid_ in selected_indices:  # Mark the selected conflicting agents to red
            self.shown_conflicts[self.conflict_listbox.get(_sid_)][1] = True
            conf = self.shown_conflicts[self.conflict_listbox.get(_sid_)]
            if conf[0][0] != -1:
                self.change_ag_color(conf[0][0], AGENT_COLORS["collide"])
            if conf[0][1] != -1:
                self.change_ag_color(conf[0][1], AGENT_COLORS["collide"])


    def restart_timestep(self):
        self.new_time.set(self.pcf.start_tstep)
        for ag_idx in self.pcf.shown_path_agents:
            for _p_ in self.pcf.agents[ag_idx].path_objs:
                self.pcf.canvas.itemconfigure(_p_.obj, state=tk.HIDDEN)
        self.pcf.shown_path_agents.clear()

        # Reset the tasks
        if self.pcf.event_tracker:
            for ag_ in range(self.pcf.team_size):
                for tid_ in self.pcf.ag_to_task[ag_]:
                    self.show_single_task(tid_)

        self.update_curtime()


    def move_to_conflict(self, event):
        if self.is_run.get() is True:
            return

        _sid_ = event.widget.curselection()[0]  # get all selected indices
        conf = self.shown_conflicts[self.conflict_listbox.get(_sid_)]
        if conf[0][0] != -1 and conf[0][0] < self.pcf.team_size:
            self.change_ag_color(conf[0][0], AGENT_COLORS["collide"])
        if conf[0][1] != -1 and conf[0][1] < self.pcf.team_size:
            self.change_ag_color(conf[0][1], AGENT_COLORS["collide"])
        self.shown_conflicts[self.conflict_listbox.get(_sid_)][1] = True
        self.new_time.set(int(conf[0][2])-1)
        self.update_curtime()

        for (_, _agent_) in self.pcf.agents.items():
            _agent_.path = _agent_.plan_path
        self.move_agents_per_timestep()
        time.sleep(1.5)

        for (_, _agent_) in self.pcf.agents.items():
            _agent_.path = _agent_.exec_path
        self.new_time.set(int(conf[0][2])-1)
        self.update_curtime()


    def move_to_event(self, event):
        if self.is_run.get() is True:
            return
        _sid_ = event.widget.curselection()[0]  # get all selected indices
        eve_str:str = self.event_listbox.get(_sid_)
        cur_eve:Tuple[int,int,int,str] = self.shown_events[eve_str]
        new_t = max(cur_eve[0]-1, 0)  # move to one timestep ahead the event
        self.new_time.set(new_t)
        self.update_curtime()

    def __move_from(self, event):
        """ Remember previous coordinates for scrolling with the mouse """
        self.pcf.canvas.scan_mark(event.x, event.y)

    def __move_to(self, event):
        """ Drag (move) canvas to the new position """
        self.pcf.canvas.scan_dragto(event.x, event.y, gain=1)


    def __wheel(self, event):
        """ Zoom with mouse wheel """
        scale = 1.0
        # Respond to Linux (event.num) or Windows/macOS (event.delta) wheel event
        if event.num == 5 or event.delta < 0:  # scroll down, smaller
            threshold = round(min(self.pcf.width, self.pcf.height) * self.pcf.tile_size)
            if threshold < 30:
                return  # image is less than 30 pixels
            scale /= 1.10
            self.pcf.tile_size /= 1.10
        if event.num == 4 or event.delta > 0:  # scroll up, bigger
            scale *= 1.10
            self.pcf.tile_size *= 1.10
        self.pcf.canvas.scale("all", 0, 0, scale, scale)  # rescale all objects
        for child_widget in self.pcf.canvas.find_withtag("text"):
            self.pcf.canvas.itemconfigure(child_widget,
                                          font=("Arial", int(self.pcf.tile_size // 2)))
        for child_widget in self.pcf.canvas.find_withtag("hwy"):
            self.pcf.canvas.itemconfigure(child_widget,
                                          font=("Arial", int(self.pcf.tile_size*1.2)))
        self.pcf.canvas.configure(scrollregion = self.pcf.canvas.bbox("all"))


    def resume_zoom(self):
        __scale = self.pcf.ppm * self.pcf.moves / self.pcf.tile_size
        self.pcf.canvas.scale("all", 0, 0, __scale, __scale)
        self.pcf.tile_size = self.pcf.ppm * self.pcf.moves
        for child_widget in self.pcf.canvas.find_withtag("text"):
            self.pcf.canvas.itemconfigure(child_widget,
                                          font=("Arial", int(self.pcf.tile_size // 2)))
        for child_widget in self.pcf.canvas.find_withtag("hwy"):
            self.pcf.canvas.itemconfigure(child_widget,
                                          font=("Arial", int(self.pcf.tile_size*1.2)))
        self.pcf.canvas.configure(scrollregion = self.pcf.canvas.bbox("all"))
        self.pcf.canvas.update()


    def show_ag_plan_by_click(self, event):
        item = self.pcf.canvas.find_closest(event.x, event.y)[0]
        tags:Set[str] = self.pcf.canvas.gettags(item)
        ag_idx = -1
        for _tt_ in tags:
            if _tt_.isnumeric():
                ag_idx = int(_tt_)  # get the id of the agent
                break
        if ag_idx == -1:
            return
        self.show_ag_plan(ag_idx)


    def show_ag_plan(self, ag_idx):
        if ag_idx in self.pcf.shown_path_agents:  # Remove ag_id if it's already in the set
            self.pcf.shown_path_agents.remove(ag_idx)
            for _p_ in self.pcf.agents[ag_idx].path_objs:
                self.pcf.canvas.itemconfigure(_p_.obj, state=tk.HIDDEN)
                self.pcf.canvas.tag_lower(_p_.obj)
        else:
            self.pcf.shown_path_agents.add(ag_idx)  # Add ag_id to the set
            for _pid_ in range(self.pcf.cur_tstep+1, len(self.pcf.agents[ag_idx].path_objs)):
                self.pcf.canvas.itemconfigure(self.pcf.agents[ag_idx].path_objs[_pid_].obj,
                                              state=tk.DISABLED)
                self.pcf.canvas.tag_raise(self.pcf.agents[ag_idx].path_objs[_pid_].obj)

        # Reset the tasks if no agent needs to show its path
        if not self.pcf.shown_path_agents:
            for ag_ in range(self.pcf.team_size):
                for tid_ in self.pcf.ag_to_task[ag_]:
                    self.show_single_task(tid_)
            return

        # Hide tasks that are not in ag_id
        for ag_ in range(self.pcf.team_size):
            if ag_ in self.pcf.shown_path_agents:
                for tid_ in self.pcf.ag_to_task[ag_]:
                    self.show_single_task(tid_)
            else:
                for tid_ in self.pcf.ag_to_task[ag_]:
                    self.hide_single_task(tid_)


    def mark_conf_agents(self) -> None:
        self.conflict_listbox.select_clear(0, self.conflict_listbox.size())
        for conf in self.shown_conflicts.values():
            if conf[0][0] != -1 and conf[0][0] < self.pcf.team_size:
                if self.show_all_conf_ag.get():
                    self.pcf.canvas.itemconfig(self.pcf.agents[conf[0][0]].agent_obj.obj,
                                               fill=AGENT_COLORS["collide"])
                else:
                    self.pcf.canvas.itemconfig(self.pcf.agents[conf[0][0]].agent_obj.obj,
                                               fill=self.pcf.agents[conf[0][0]].agent_obj.color)

            if conf[0][1] != -1 and conf[0][1] < self.pcf.team_size:
                if self.show_all_conf_ag.get():
                    self.pcf.canvas.itemconfig(self.pcf.agents[conf[0][1]].agent_obj.obj,
                                               fill=AGENT_COLORS["collide"])
                else:
                    self.pcf.canvas.itemconfig(self.pcf.agents[conf[0][1]].agent_obj.obj,
                                               fill=self.pcf.agents[conf[0][1]].agent_obj.color)
            conf[1] = False


    def show_grid(self) -> None:
        if self.is_grid.get() is True:
            for _line_ in self.pcf.grids:
                self.pcf.canvas.itemconfig(_line_, state=tk.NORMAL)
        else:
            for _line_ in self.pcf.grids:
                self.pcf.canvas.itemconfig(_line_, state=tk.HIDDEN)


    def show_heat_map(self) -> None:
        if self.is_heat_map.get() is True:
            for item in self.pcf.heat_grids:
                self.pcf.canvas.itemconfig(item.obj, state=tk.DISABLED)
                self.pcf.canvas.itemconfig(item.text, state=tk.DISABLED)
        else:
            for item in self.pcf.heat_grids:
                self.pcf.canvas.itemconfig(item.obj, state=tk.HIDDEN)
                self.pcf.canvas.itemconfig(item.text, state=tk.HIDDEN)


    def show_highway(self) -> None:
        if self.is_highway.get() is True:
            for item in self.pcf.highway:
                self.pcf.canvas.itemconfig(item["obj"], state=tk.DISABLED)
        else:
            for item in self.pcf.highway:
                self.pcf.canvas.itemconfig(item["obj"], state=tk.HIDDEN)


    def show_heuristic_map(self) -> None:
        if self.is_heuristic_map.get() is True:
            for item in self.pcf.heuristic_grids:
                self.pcf.canvas.itemconfig(item.obj, state=tk.DISABLED)
                self.pcf.canvas.itemconfig(item.text, state=tk.DISABLED)
        else:
            for item in self.pcf.heuristic_grids:
                self.pcf.canvas.itemconfig(item.obj, state=tk.HIDDEN)
                self.pcf.canvas.itemconfig(item.text, state=tk.HIDDEN)


    def show_search_tree(self, _) -> None:
        if self.pcf.cur_tree == self.tree_shown.get():
            return

        # Hide previous search tree
        if self.pcf.cur_tree != "None":
            for item in self.pcf.search_tree_grids[self.pcf.cur_tree]:
                self.pcf.canvas.itemconfig(item.obj, state=tk.HIDDEN)
                self.pcf.canvas.itemconfig(item.text, state=tk.HIDDEN)

        # Show new search tree
        self.pcf.cur_tree = self.tree_shown.get()
        if self.pcf.cur_tree == "None":
            return
        for item in self.pcf.search_tree_grids[self.pcf.cur_tree]:
            self.pcf.canvas.itemconfig(item.obj, state=tk.DISABLED)
            self.pcf.canvas.itemconfig(item.text, state=tk.DISABLED)


    def show_agent_index(self) -> None:
        _state_ = tk.DISABLED if self.show_ag_idx.get() is True else tk.HIDDEN
        _ts_ = tk.DISABLED if (self.show_ag_idx.get() is True and\
            self.show_static.get() is True) else tk.HIDDEN
        for (_, _agent_) in self.pcf.agents.items():
            
            self.pcf.canvas.itemconfig(_agent_.agent_obj.text, state=_state_)
            self.pcf.canvas.itemconfig(_agent_.start_obj.text, state=_ts_)


    def show_task_index(self) -> None:
        for (_, task) in self.pcf.tasks.items():
            self.pcf.canvas.itemconfig(task.task_obj.text, state=tk.HIDDEN)
            if not self.show_task_idx.get():
                self.pcf.canvas.itemconfig(task.task_obj.text, state=tk.HIDDEN)
            elif self.task_shown.get() == "all":
                self.pcf.canvas.itemconfig(task.task_obj.text, state=tk.DISABLED)
            elif self.task_shown.get() == "none":
                self.pcf.canvas.itemconfig(task.task_obj.text, state=tk.HIDDEN)
            elif self.task_shown.get() == "assigned":
                if task.state in ["assigned", "newlyassigned"]:
                    self.pcf.canvas.itemconfig(task.task_obj.text, state=tk.DISABLED)
            elif task.state == self.task_shown.get():
                self.pcf.canvas.itemconfig(task.task_obj.text, state=tk.DISABLED)


    def show_tasks(self) -> None:
        for (_, task) in self.pcf.tasks.items():
            self.pcf.canvas.itemconfig(task.task_obj.obj, state=tk.HIDDEN)
            if self.task_shown.get() == "all":
                self.pcf.canvas.itemconfig(task.task_obj.obj, state=tk.DISABLED)
            elif self.task_shown.get() == "none":
                self.pcf.canvas.itemconfig(task.task_obj.obj, state=tk.HIDDEN)
            elif self.task_shown.get() == "assigned":
                if task.state in ["assigned", "newlyassigned"]:
                    self.pcf.canvas.itemconfig(task.task_obj.obj, state=tk.DISABLED)
            elif task.state == self.task_shown.get():
                self.pcf.canvas.itemconfig(task.task_obj.obj, state=tk.DISABLED)
        self.show_task_index()


    def show_tasks_by_click(self, _) -> None:
        self.show_tasks()


    def show_single_task(self, tid) -> None:
        tsk = self.pcf.tasks[tid]
        self.hide_single_task(tid)

        if self.task_shown.get() == "none":
            return

        if self.task_shown.get() == "all":
            if self.pcf.canvas.itemcget(tsk.task_obj.obj, "state") == tk.HIDDEN:
                self.pcf.canvas.itemconfig(tsk.task_obj.obj, state=tk.DISABLED)
                if self.show_task_idx.get():
                    self.pcf.canvas.itemconfig(tsk.task_obj.text, state=tk.DISABLED)
                else:
                    self.pcf.canvas.itemconfig(tsk.task_obj.text, state=tk.HIDDEN)
            return

        if self.task_shown.get() == "assigned":
            if tsk.state in ["assigned", "newlyassigned"]:
                self.pcf.canvas.itemconfig(tsk.task_obj.obj, state=tk.DISABLED)
                if self.show_task_idx.get():
                    self.pcf.canvas.itemconfig(tsk.task_obj.text, state=tk.DISABLED)
                else:
                    self.pcf.canvas.itemconfig(tsk.task_obj.text, state=tk.HIDDEN)
            return

        if tsk.state == self.task_shown.get():
            self.pcf.canvas.itemconfig(tsk.task_obj.obj, state=tk.DISABLED)
            if self.show_task_idx.get():
                self.pcf.canvas.itemconfig(tsk.task_obj.text, state=tk.DISABLED)
            else:
                self.pcf.canvas.itemconfig(tsk.task_obj.text, state=tk.HIDDEN)
            return


    def hide_single_task(self, tid) -> None:
        task = self.pcf.tasks[tid]
        self.pcf.canvas.itemconfig(task.task_obj.obj, state=tk.HIDDEN)
        self.pcf.canvas.itemconfig(task.task_obj.text, state=tk.HIDDEN)


    def show_static_loc(self) -> None:
        _os_ = tk.DISABLED if self.show_static.get() is True else tk.HIDDEN
        _ts_ = tk.DISABLED if (self.show_ag_idx.get() is True and\
            self.show_static.get() is True) else tk.HIDDEN
        for (_, _agent_) in self.pcf.agents.items():
            self.pcf.canvas.itemconfig(_agent_.start_obj.obj, state=_os_)
            self.pcf.canvas.itemconfig(_agent_.start_obj.text, state=_ts_)


    def move_agents_per_timestep(self) -> None:
        if self.pcf.cur_tstep+1 > min(self.pcf.makespan, self.pcf.end_tstep):
            return

        self.next_button.config(state=tk.DISABLED)
        _rad_ = ((1 - 2*DIR_OFFSET) - 0.1*2) * self.pcf.tile_size/2

        # Update the next timestep for each agent
        next_tstep = {}
        for (ag_id, agent) in self.pcf.agents.items():
            next_t = min(self.pcf.cur_tstep+1 - self.pcf.start_tstep, len(agent.path)-1)
            next_tstep[ag_id] = next_t

        for _m_ in range(self.pcf.moves):
            if _m_ == self.pcf.moves // 2:
                self.timestep_label.config(text = f"Timestep: {self.pcf.cur_tstep+1:03d}")

            for (ag_id, agent) in self.pcf.agents.items():
                cur_angle = get_angle(agent.agent_obj.loc[2])
                direction = (agent.path[next_tstep[ag_id]][1] - agent.agent_obj.loc[1],
                             agent.path[next_tstep[ag_id]][0] - agent.agent_obj.loc[0])
                cur_move = (direction[0] * (self.pcf.tile_size / self.pcf.moves),
                            direction[1] * (self.pcf.tile_size / self.pcf.moves))
                cur_rotation = get_rotation(agent.agent_obj.loc[2],
                                            agent.path[next_tstep[ag_id]][2])
                next_ang = cur_rotation*(math.pi/2)/(self.pcf.moves)

                # Move agent
                _cos = math.cos(cur_angle + next_ang * (_m_+1)) - math.cos(cur_angle+next_ang*_m_)
                _sin = -1 * (math.sin(cur_angle+ next_ang*(_m_+1))-math.sin(cur_angle+next_ang*_m_))
                self.pcf.canvas.move(agent.agent_obj.obj, cur_move[0], cur_move[1])
                self.pcf.canvas.move(agent.agent_obj.text, cur_move[0], cur_move[1])
                if self.pcf.agent_model == "MAPF_T":
                    self.pcf.canvas.move(agent.dir_obj, cur_move[0], cur_move[1])
                    self.pcf.canvas.move(agent.dir_obj, _rad_ * _cos, _rad_ * _sin)
            self.pcf.canvas.update()
            time.sleep(self.pcf.delay)

        # Update the location of each agent
        for (ag_id, agent) in self.pcf.agents.items():
            agent.agent_obj.loc = (agent.path[next_tstep[ag_id]][0],
                                   agent.path[next_tstep[ag_id]][1],
                                   agent.path[next_tstep[ag_id]][2])
        self.pcf.cur_tstep += 1
        self.next_button.config(state=tk.NORMAL)

        # Change tasks' states after cur_tstep += 1
        if not self.pcf.event_tracker:
            return

        prev_aid = max(self.pcf.event_tracker["aid"]-1, 0)
        if self.pcf.cur_tstep-1 == self.pcf.event_tracker["aTime"][prev_aid]:
            # from newly assigned to assigned
            for (tid, ag_id) in self.pcf.events["assigned"][self.pcf.cur_tstep-1].items():
                self.pcf.tasks[tid].state = "assigned"
                self.change_task_color(tid, TASK_COLORS["assigned"])
                self.change_ag_color(ag_id, AGENT_COLORS["assigned"])
                if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                    self.show_single_task(tid)

        if self.pcf.cur_tstep == self.pcf.event_tracker["aTime"][self.pcf.event_tracker["aid"]]:
            # from unassigned to newly assigned
            for (tid, ag_id) in self.pcf.events["assigned"][self.pcf.cur_tstep].items():
                self.pcf.tasks[tid].state = "newlyassigned"
                self.change_task_color(tid, TASK_COLORS["newlyassigned"])
                self.change_ag_color(ag_id, AGENT_COLORS["newlyassigned"])
                if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                    self.show_single_task(tid)
            self.pcf.event_tracker["aid"] += 1

        if self.pcf.cur_tstep == self.pcf.event_tracker["fTime"][self.pcf.event_tracker["fid"]]:
            # from assigned to finished
            for tid in self.pcf.events["finished"][self.pcf.cur_tstep]:
                self.pcf.tasks[tid].state = "finished"
                self.change_task_color(tid, TASK_COLORS["finished"])
                if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                    self.show_single_task(tid)
            self.pcf.event_tracker["fid"] += 1
        self.show_tasks()
        for (ag_id, agent) in self.pcf.agents.items():
            self.pcf.canvas.tag_raise(agent.agent_obj.obj, 'all')


    def back_agents_per_timestep(self) -> None:
        if self.pcf.cur_tstep == self.pcf.start_tstep:
            return

        self.prev_button.config(state=tk.DISABLED)
        prev_timestep = max(self.pcf.cur_tstep-1, 0)

        # Move the event tracker backward
        prev_aid = max(self.pcf.event_tracker["aid"]-1, 0)
        prev_fid = max(self.pcf.event_tracker["fid"]-1, 0)
        prev_agn_time = self.pcf.event_tracker["aTime"][prev_aid]
        prev_fin_time = self.pcf.event_tracker["fTime"][prev_fid]

        if self.pcf.cur_tstep == prev_fin_time:  # from finished to assigned
            for (tid, ag_id) in self.pcf.events["finished"][prev_fin_time].items():
                assert self.pcf.tasks[tid].state == "finished"
                self.pcf.tasks[tid].state = "assigned"
                self.change_task_color(tid, TASK_COLORS["assigned"])
                if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                    self.show_single_task(tid)
            self.pcf.event_tracker["fid"] = prev_fid

        if self.pcf.cur_tstep == prev_agn_time:  # from newly assigned to unassigned
            for (tid, ag_id) in self.pcf.events["assigned"][prev_agn_time].items():
                assert self.pcf.tasks[tid].state == "newlyassigned"
                self.pcf.tasks[tid].state = "unassigned"
                self.change_task_color(tid, TASK_COLORS["unassigned"])
                self.change_ag_color(ag_id, AGENT_COLORS["assigned"])
                if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                    self.show_single_task(tid)
            self.pcf.event_tracker["aid"] = prev_aid
            prev_aid = max(self.pcf.event_tracker["aid"]-1, 0)
            prev_agn_time = self.pcf.event_tracker["aTime"][prev_aid]

        if prev_timestep == prev_agn_time:  # from assigned to newly assigned
            for (tid, ag_id) in self.pcf.events["assigned"][prev_agn_time].items():
                assert self.pcf.tasks[tid].state == "assigned"
                self.pcf.tasks[tid].state = "newlyassigned"
                self.change_task_color(tid, TASK_COLORS["newlyassigned"])
                self.change_ag_color(ag_id, AGENT_COLORS["newlyassigned"])
                if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                    self.show_single_task(tid)

        # Compute the previous location
        prev_loc:Dict[int, Tuple[int, int]] = {}
        relative_prev_t = prev_timestep - self.pcf.start_tstep
        for (ag_id, agent) in self.pcf.agents.items():
            if relative_prev_t > len(agent.path)-1:
                prev_loc[ag_id] = (agent.path[-1][0],
                                   agent.path[-1][1],
                                   agent.path[-1][2])
            else:
                prev_loc[ag_id] = (agent.path[relative_prev_t][0],
                                   agent.path[relative_prev_t][1],
                                   agent.path[relative_prev_t][2])

        # Move the agents backward
        _rad_ = ((1 - 2*DIR_OFFSET) - 0.1*2) * self.pcf.tile_size/2
        for _m_ in range(self.pcf.moves):
            if _m_ == self.pcf.moves // 2:
                self.timestep_label.config(text = f"Timestep: {prev_timestep:03d}")
            for (ag_id, agent) in self.pcf.agents.items():
                cur_angle = get_angle(agent.agent_obj.loc[2])
                direction = (prev_loc[ag_id][1] - agent.agent_obj.loc[1],
                             prev_loc[ag_id][0] - agent.agent_obj.loc[0])
                cur_move = (direction[0] * (self.pcf.tile_size / self.pcf.moves),
                            direction[1] * (self.pcf.tile_size / self.pcf.moves))
                cur_rotation = get_rotation(agent.agent_obj.loc[2], prev_loc[ag_id][2])
                next_ang = cur_rotation*(math.pi/2)/(self.pcf.moves)

                # Move agent
                _cos = math.cos(cur_angle+next_ang*(_m_+1)) - math.cos(cur_angle + next_ang*_m_)
                _sin = -1*(math.sin(cur_angle+next_ang*(_m_+1))-math.sin(cur_angle + next_ang*_m_))
                self.pcf.canvas.move(agent.agent_obj.obj, cur_move[0], cur_move[1])
                self.pcf.canvas.move(agent.agent_obj.text, cur_move[0], cur_move[1])
                if self.pcf.agent_model == "MAPF_T":
                    self.pcf.canvas.move(agent.dir_obj, cur_move[0], cur_move[1])
                    self.pcf.canvas.move(agent.dir_obj, _rad_*_cos, _rad_*_sin)
            self.pcf.canvas.update()
            time.sleep(self.pcf.delay)
        for (ag_id, agent) in self.pcf.agents.items():
            agent.agent_obj.loc = prev_loc[ag_id]

        self.pcf.cur_tstep = prev_timestep
        self.prev_button.config(state=tk.NORMAL)
        self.next_button.config(state=tk.NORMAL)


    def move_agents(self) -> None:
        """ Move agents constantly until pause or end_tstep is reached.
        """
        self.run_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)
        self.next_button.config(state=tk.DISABLED)
        self.prev_button.config(state=tk.DISABLED)
        self.update_button.config(state=tk.DISABLED)
        self.restart_button.config(state=tk.DISABLED)
        self.task_shown.config(state=tk.DISABLED)

        self.is_run.set(True)
        while self.pcf.cur_tstep < min(self.pcf.makespan, self.pcf.end_tstep):
            if self.is_run.get() is True:
                self.move_agents_per_timestep()
                time.sleep(self.pcf.delay * 2)
            else:
                break

        self.run_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.NORMAL)
        self.next_button.config(state=tk.NORMAL)
        self.prev_button.config(state=tk.NORMAL)
        self.update_button.config(state=tk.NORMAL)
        self.restart_button.config(state=tk.NORMAL)
        self.task_shown.config(state=tk.NORMAL)


    def pause_agents(self) -> None:
        self.is_run.set(False)
        self.pause_button.config(state=tk.DISABLED)
        self.run_button.config(state=tk.NORMAL)
        self.next_button.config(state=tk.NORMAL)
        self.prev_button.config(state=tk.NORMAL)
        self.pcf.canvas.after(200, lambda: self.pause_button.config(state=tk.NORMAL))


    def update_curtime(self) -> None:
        """ Update the agents and tasks' colors to the cur_tstep
        """
        if self.new_time.get() > self.pcf.end_tstep:
            print("The target timestep is larger than the ending timestep")
            self.new_time.set(self.pcf.end_tstep)

        self.pcf.cur_tstep = self.new_time.get()
        self.timestep_label.config(text = f"Timestep: {self.pcf.cur_tstep:03d}")

        # Change tasks' and agents' colors according to assigned timesteps
        for (tid, task) in self.pcf.tasks.items():  # Initialize all the task states to unassigned
            task.state = "unassigned"
            self.change_task_color(tid, TASK_COLORS["unassigned"])
            self.hide_single_task(tid)

        if self.pcf.event_tracker:
            for a_id, a_time in enumerate(self.pcf.event_tracker["aTime"]):
                if a_time == -1:
                    self.pcf.event_tracker["aid"] = a_id
                    break
                if a_time < self.pcf.cur_tstep:
                    for (tid, ag_id) in self.pcf.events["assigned"][a_time].items():
                        self.pcf.tasks[tid].state = "assigned"
                        self.change_task_color(tid, TASK_COLORS["assigned"])
                        self.pcf.agents[ag_id].agent_obj.color = AGENT_COLORS["assigned"]
                        if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                            self.show_single_task(tid)
                elif a_time == self.pcf.cur_tstep:
                    for (tid, ag_id) in self.pcf.events["assigned"][a_time].items():
                        self.pcf.tasks[tid].state = "newlyassigned"
                        self.change_task_color(tid, TASK_COLORS["newlyassigned"])
                        self.pcf.agents[ag_id].agent_obj.color = AGENT_COLORS["newlyassigned"]
                        if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                            self.show_single_task(tid)
                else:  # a_time > self.pcf.cur_tstep
                    self.pcf.event_tracker["aid"] = a_id
                    break

            # Change tasks' colors according to finished timesteps
            for f_id, f_time in enumerate(self.pcf.event_tracker["fTime"]):
                if f_time == -1:
                    break
                if f_time <= self.pcf.cur_tstep:
                    for (tid, ag_id) in self.pcf.events["finished"][f_time].items():
                        self.pcf.tasks[tid].state = "finished"
                        self.change_task_color(tid, TASK_COLORS["finished"])
                        if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                            self.show_single_task(tid)
                else:
                    self.pcf.event_tracker["fid"] = f_id
                    break

        for (ag_id, agent_) in self.pcf.agents.items():
            # Check colliding agents
            show_collide = False
            if (self.show_all_conf_ag.get() and agent_ in self.pcf.conflict_agents) or \
                self.pcf.canvas.itemcget(agent_.agent_obj.obj, "fill") == AGENT_COLORS["collide"]:
                show_collide = True

            # Re-generate agent objects
            tstep = min(self.pcf.cur_tstep - self.pcf.start_tstep, len(agent_.path)-1)
            self.pcf.canvas.delete(agent_.agent_obj.obj)
            self.pcf.canvas.delete(agent_.agent_obj.text)
            agent_.agent_obj = self.pcf.render_obj(ag_id, agent_.path[tstep], "oval",
                                                   agent_.agent_obj.color,
                                                   tk.NORMAL, 0.05, str(ag_id))
            if self.pcf.agent_model == "MAPF_T":
                self.pcf.canvas.delete(agent_.dir_obj)
                dir_loc = get_dir_loc(agent_.path[tstep])
                agent_.dir_obj = self.pcf.canvas.create_oval(dir_loc[0] * self.pcf.tile_size,
                                                             dir_loc[1] * self.pcf.tile_size,
                                                             dir_loc[2] * self.pcf.tile_size,
                                                             dir_loc[3] * self.pcf.tile_size,
                                                             fill="navy",
                                                             tag="dir",
                                                             state=tk.DISABLED,
                                                             outline="")
            # Check colliding agents
            if show_collide:
                self.change_ag_color(ag_id, AGENT_COLORS["collide"])

        self.show_agent_index()
        self.pcf.canvas.update()



class PlanViz2024:
    """ This is the control panel of PlanViz2
    """
    AGENT_OBJ_TAG = "agent_obj"
    AGENT_DIR_TAG = "agent_dir"
    AGENT_START_OBJ_TAG = "agent_start_obj"
    AGENT_TEXT_TAG = "agent_text"
    AGENT_START_TEXT_TAG = "agent_start_text"

    def __init__(self, plan_config, _grid, _ag_idx, _task_idx, _static, _conf_ag):
        print("===== Initialize PlanViz2    =====")

        self.init_pcf(plan_config)

        # Generate the UI panel
        print("Rendering the panel... ", end="")

        self.is_run = tk.BooleanVar()
        self.is_grid = tk.BooleanVar()
        self.show_ag_idx = tk.BooleanVar()
        self.show_task_idx = tk.BooleanVar()
        self.show_static = tk.BooleanVar()
        self.show_all_conf_ag = tk.BooleanVar()
        self.show_agent_path = tk.BooleanVar()
        self.show_hover_loc = tk.BooleanVar()
        self.is_heat_map = tk.BooleanVar()
        self.is_highway = tk.BooleanVar()
        self.is_heuristic_map = tk.BooleanVar()

        self.is_run.set(False)
        self.is_grid.set(_grid)
        self.show_ag_idx.set(_ag_idx)
        self.show_task_idx.set(_task_idx)
        self.show_static.set(_static)
        self.show_all_conf_ag.set(_conf_ag)
        self.show_hover_loc.set(False)
        self.is_heat_map.set(False)
        self.is_highway.set(False)
        self.is_heuristic_map.set(False)
        self.listbox_monospace_font = font.Font(family="Courier", size=TEXT_SIZE)

        gui_window = self.pcf.window
        self.gui_column = 1
        if (not self.pcf.use_viewport_mode) and \
            (self.pcf.width+1) * self.pcf.tile_size > 0.5 * self.pcf.window.winfo_screenwidth():
            gui_window = tk.Toplevel()
            gui_window.transient(self.pcf.window)
            gui_window.lift()
            gui_window.title("UI Panel")
            gui_window.config(width=300, height=(self.pcf.height+1) * self.pcf.tile_size)
            self.gui_column = 0
        self.frame = tk.Frame(gui_window)
        self.frame.grid(row=0, column=self.gui_column,sticky="nsew")
        self.row_idx = 0
        self.pop_gui_window = None
        self.pop_event_listbox = None
        self.pop_location_listbox = None
        self.event_count_frame = None
        self.event_count_value_labels:Dict[str, tk.Label] = {}
        self.event_count_times:List[int] = []
        self.event_count_prefix:Dict[str, List[int]] = {
            "assigned": [],
            "errand_finished": [],
            "task_finished": [],
        }
        self.minimap_canvas = None
        self.minimap_photo = None
        self.minimap_image_obj = None
        self.minimap_view_obj = None
        self.minimap_dragging = False
        
        self.time_label = tk.Label(self.frame,
                                   text=f"Time: {self.pcf.cur_tstep:03d}",
                                   font=("Arial", TEXT_SIZE + 10))
        self.time_label.grid(row=self.row_idx, column=0, columnspan=10, sticky="w")
        self.set_time_labels(self.pcf.cur_tstep)
        self.row_idx += 1
        self.mouse_loc_label = tk.Label(self.frame,
                                       text="Mouse Position: ",
                                       font=("Arial", TEXT_SIZE + 10))
        self.mouse_loc_label.grid(row=self.row_idx, column=0, columnspan=10, sticky="w")
        self.row_idx += 1
        self.init_minimap()

        self.init_button()
        self.init_label()

        print("=====          DONE         =====")


    def set_time_labels(self, timeline_value:int) -> None:
        """Update the displayed time based on the current timeline value."""
        self.time_label.config(text=f"Time: {int(timeline_value):03d}")


    def agent_has_selected_conflict(self, ag_idx:int) -> bool:
        for conf in self.shown_conflicts.values():
            if not conf[1]:
                continue
            if len(conf[0]) == 5:
                _, agent1, agent2, _, _ = conf[0]
            else:
                agent1, agent2, _, _ = conf[0]
            if ag_idx == agent1 or ag_idx == agent2:
                return True
        return False


    def update_agent_colors(self) -> None:
        for ag_idx, agent in self.pcf.agents.items():
            shown_color = AGENT_COLORS[self.pcf.get_agent_status(ag_idx, self.pcf.cur_tstep).color_key]
            if self.show_all_conf_ag.get() and ag_idx in self.pcf.conflict_agents:
                shown_color = AGENT_COLORS["collide"]
            elif self.agent_has_selected_conflict(ag_idx):
                shown_color = AGENT_COLORS["collide"]

            if agent.agent_obj.color == shown_color:
                continue
            self.pcf.canvas.itemconfig(agent.agent_obj.obj, fill=shown_color)
            agent.agent_obj.color = shown_color


    def init_pcf(self, plan_config):
        # Load the yaml file or the input arguments
        self.pcf:PlanConfig2024 = plan_config
        self._init_agent_canvas_tags()
        
        if platform.system() == "Darwin":
            self.pcf.canvas.event_add("<<RightClick>>", "<Button-2>")
            self.pcf.canvas.event_add("<<CtrlRightClick>>", "<Control-Button-2>")
            self.pcf.canvas.event_add("<<MiddleClick>>", "<Button-3>")
        else:
            self.pcf.canvas.event_add("<<RightClick>>", "<Button-3>")
            self.pcf.canvas.event_add("<<CtrlRightClick>>", "<Control-Button-3>")
            self.pcf.canvas.event_add("<<MiddleClick>>", "<Button-2>")

        self.double_click_threshold = 0.1  # 300ms
        self.drag_move_threshold = 5       # 5 pixels
        self.last_click_time = 0
        self.last_click_pos = (0, 0)
        self.dragging = False
        self.right_click_agent = -1
        self.right_click_all_tasks_idx = []
        self.right_click_status = "left"
        self.pcf.canvas.bind("<<RightClick>>", self.right_click)
        self.pcf.canvas.bind("<Motion>", self.on_hover)
        if self.pcf.use_viewport_mode:
            self.pcf.canvas.bind("<Configure>", self.on_canvas_configure)

        # This is what enables using the mouse:
        self.pcf.canvas.bind("<ButtonPress-1>", self.check_left_click)
        self.pcf.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.pcf.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        
        # linux scroll
        self.pcf.canvas.bind("<Button-4>", self.__wheel)
        self.pcf.canvas.bind("<Button-5>", self.__wheel)
        # windows scroll
        self.pcf.canvas.bind("<MouseWheel>",self.__wheel)


    def _tag_agent_dynamic_canvas_items(self, agent_) -> None:
        self.pcf.canvas.addtag_withtag(self.AGENT_OBJ_TAG, agent_.agent_obj.obj)
        self.pcf.canvas.addtag_withtag(self.AGENT_TEXT_TAG, agent_.agent_obj.text)
        if agent_.dir_obj:
            self.pcf.canvas.addtag_withtag(self.AGENT_DIR_TAG, agent_.dir_obj)


    def _tag_agent_static_canvas_items(self, agent_) -> None:
        self.pcf.canvas.addtag_withtag(self.AGENT_START_OBJ_TAG, agent_.start_obj.obj)
        self.pcf.canvas.addtag_withtag(self.AGENT_START_TEXT_TAG, agent_.start_obj.text)


    def _init_agent_canvas_tags(self) -> None:
        for _, agent_ in self.pcf.agents.items():
            self._tag_agent_dynamic_canvas_items(agent_)
            self._tag_agent_static_canvas_items(agent_)

    def init_minimap(self):
        if not self.pcf.use_viewport_mode:
            return

        minimap_label = tk.Label(self.frame, text="Minimap", font=("Arial", TEXT_SIZE))
        minimap_label.grid(row=self.row_idx, column=0, columnspan=3, sticky="w")
        self.row_idx += 1

        self.minimap_canvas = tk.Canvas(self.frame,
                                        width=self.pcf.minimap_width_px,
                                        height=self.pcf.minimap_height_px,
                                        bg="white",
                                        highlightthickness=1,
                                        highlightbackground="#666666")
        self.minimap_canvas.grid(row=self.row_idx, column=0, columnspan=3, sticky="w")
        self.minimap_canvas.bind("<ButtonPress-1>", self.on_minimap_press)
        self.minimap_canvas.bind("<B1-Motion>", self.on_minimap_drag)
        self.minimap_canvas.bind("<ButtonRelease-1>", self.on_minimap_release)

        if self.pcf.base_env_image is not None:
            source_image = self.pcf.base_env_image
            if self.pcf.show_coord_labels:
                padded_image = Image.new(
                    "RGBA",
                    (self.pcf.width + 1, self.pcf.height + 1),
                    (255, 255, 255, 0),
                )
                padded_image.paste(self.pcf.base_env_image, (0, 0))
                source_image = padded_image

            scaled = source_image.resize(
                (self.pcf.minimap_render_width_px, self.pcf.minimap_render_height_px),
                Image.Resampling.NEAREST,
            )
            self.minimap_photo = ImageTk.PhotoImage(scaled)
            self.minimap_image_obj = self.minimap_canvas.create_image(
                self.pcf.minimap_offset_x_px,
                self.pcf.minimap_offset_y_px,
                anchor="nw",
                image=self.minimap_photo,
            )

        self.minimap_view_obj = self.minimap_canvas.create_rectangle(
            0, 0, 1, 1, outline="#cf2b24", width=2
        )
        self.row_idx += 1


    def init_button(self):
        # ---------- List of buttons ------------------------------- #
        self.run_button = tk.Button(self.frame, text="Play",
                                    font=("Arial",TEXT_SIZE),
                                    command=self.move_agents)
        self.run_button.grid(row=self.row_idx, column=0, sticky="nsew")
        self.pause_button = tk.Button(self.frame, text="Pause",
                                      font=("Arial",TEXT_SIZE),
                                      command=self.pause_agents)
        self.pause_button.grid(row=self.row_idx, column=1, sticky="nsew")
        self.resume_zoom_button = tk.Button(self.frame, text="Fullsize",
                                            font=("Arial",TEXT_SIZE),
                                            command=self.resume_zoom)
        self.resume_zoom_button.grid(row=self.row_idx, column=2, columnspan=2, sticky="nsew")
        self.row_idx += 1

        self.next_button = tk.Button(self.frame, text="Next",
                                     font=("Arial",TEXT_SIZE),
                                     command=self.move_agents_per_timestep)
        self.next_button.grid(row=self.row_idx, column=0, sticky="nsew")
        self.prev_button = tk.Button(self.frame, text="Prev",
                                     font=("Arial",TEXT_SIZE),
                                     command=self.back_agents_per_timestep)
        self.prev_button.grid(row=self.row_idx, column=1, sticky="nsew")
        self.restart_button = tk.Button(self.frame, text="Restart",
                                        font=("Arial",TEXT_SIZE),
                                        command=self.restart_timestep)
        self.restart_button.grid(row=self.row_idx, column=2, columnspan=2, sticky="nsew")
        self.row_idx += 1

        # ---------- List of checkboxes ---------------------------- #
        self.grid_button = tk.Checkbutton(self.frame, text="Show grids",
                                          font=("Arial",TEXT_SIZE),
                                          variable=self.is_grid,
                                          onvalue=True, offvalue=False,
                                          command=self.show_grid)
        self.grid_button.grid(row=self.row_idx, column=0, columnspan=2, sticky="w")
        self.row_idx += 1

        self.id_button = tk.Checkbutton(self.frame, text="Show agent indices",
                                        font=("Arial",TEXT_SIZE),
                                        variable=self.show_ag_idx, onvalue=True, offvalue=False,
                                        command=self.show_agent_index)
        self.id_button.grid(row=self.row_idx, column=0, columnspan=2, sticky="w")
        self.row_idx += 1

        self.id_button2 = tk.Checkbutton(self.frame, text="Show task indices",
                                         font=("Arial",TEXT_SIZE),
                                         variable=self.show_task_idx, onvalue=True, offvalue=False,
                                         command=self.show_task_index)
        self.id_button2.grid(row=self.row_idx, column=0, columnspan=2, sticky="w")
        self.row_idx += 1

        self.static_button = tk.Checkbutton(self.frame, text="Show start locations",
                                            font=("Arial",TEXT_SIZE),
                                            variable=self.show_static, onvalue=True, offvalue=False,
                                            command=self.show_static_loc)
        self.static_button.grid(row=self.row_idx, column=0, columnspan=2, sticky="w")
        self.row_idx += 1

        self.show_all_conf_ag_button = tk.Checkbutton(self.frame, text="Show colliding agents",
                                                      font=("Arial",TEXT_SIZE),
                                                      variable=self.show_all_conf_ag,
                                                      onvalue=True, offvalue=False,
                                                      command=self.mark_conf_agents)
        self.show_all_conf_ag_button.grid(row=self.row_idx, column=0, columnspan=2, sticky="w")
        self.row_idx += 1
        
        self.show_all_conf_ag_button = tk.Checkbutton(self.frame, text="Show selected agent path",
                                                      font=("Arial",TEXT_SIZE),
                                                      variable=self.show_agent_path,
                                                      onvalue=True, offvalue=False,
                                                      command=self.off_agent_path)
        self.show_all_conf_ag_button.grid(row=self.row_idx, column=0, columnspan=2, sticky="w")
        self.row_idx += 1
        
                
        self.show_hover_loc_button = tk.Checkbutton(self.frame, text="Show location when mouse hover",
                                                      font=("Arial",TEXT_SIZE),
                                                      variable=self.show_hover_loc,
                                                      onvalue=True, offvalue=False)
        self.show_hover_loc_button.grid(row=self.row_idx, column=0, columnspan=2, sticky="w")
        self.row_idx += 1


    def init_label(self):
        # ---------- Show tasks according to their states ---------- #
        task_label = tk.Label(self.frame, text = "Shown", font = ("Arial", TEXT_SIZE))
        task_label.grid(row=self.row_idx, column=0, columnspan=1, sticky="w")
        self.task_shown = ttk.Combobox(self.frame, width=15, state="readonly",
                                       values=["Next Errand",
                                               "Assigned Tasks",
                                               "All Tasks"
                                               ])
        self.task_shown.current(0)
        self.task_shown.bind("<<ComboboxSelected>>", self.show_tasks_by_click)
        self.task_shown.grid(row=self.row_idx, column=1, sticky="w")
        self.row_idx += 1

        # ---------- Set the starting time ------------------------- #
        st_label = tk.Label(self.frame, text="Start time", font=("Arial",TEXT_SIZE))
        st_label.grid(row=self.row_idx, column=0, columnspan=1, sticky="w")
        self.new_time = tk.IntVar(value=1)
        self.start_time_entry = tk.Entry(self.frame, width=5, textvariable=self.new_time,
                                         font=("Arial",TEXT_SIZE))
        self.start_time_entry.grid(row=self.row_idx, column=1, sticky="w")
        self.update_button = tk.Button(self.frame, text="Go", font=("Arial",TEXT_SIZE),
                                       command=self.update_curtime)
        self.update_button.grid(row=self.row_idx, column=2, sticky="w")
        self.row_idx += 1

        self.init_color_legend()

        # ---------- Show the list of errors ----------------------- #
        err_label = tk.Label(self.frame, text="Most recent of errors", font=("Arial",TEXT_SIZE))
        err_label.grid(row=self.row_idx, column=0, columnspan=3, sticky="w")
        self.row_idx += 1

        self.shown_conflicts:Dict[str, List[List,bool]] = {}
        self.conflict_listbox = tk.Listbox(self.frame,
                                           width=35,
                                           height=9,
                                           font=("Arial",TEXT_SIZE),
                                           selectmode=tk.EXTENDED)

        self.conflict_listbox.grid(row=self.row_idx, column=0, columnspan=5, sticky="w")
        self.conflict_listbox.bind("<<ListboxSelect>>", self.select_conflict)
        self.conflict_listbox.bind("<Double-1>", self.move_to_conflict)

        scrollbar = tk.Scrollbar(self.frame, orient="vertical", width=20)
        self.conflict_listbox.config(yscrollcommand = scrollbar.set)
        scrollbar.config(command=self.conflict_listbox.yview)
        scrollbar.grid(row=self.row_idx, column=3, sticky="ns")
        self.row_idx += 1

        # ---------- Show the list of events ----------------------- #
        event_label = tk.Label(self.frame, text="Most recent of events", font=("Arial",TEXT_SIZE))
        event_label.grid(row=self.row_idx, column=0, columnspan=3, sticky="w")
        self.row_idx += 1

        self.shown_events:Dict[str, Tuple[int,int,int,int,str]] = {}
        self.event_listbox = tk.Listbox(self.frame,
                                        width=35,
                                        height=9,
                                        font=("Arial",TEXT_SIZE),
                                        selectmode=tk.EXTENDED)
        

        self.event_listbox.grid(row=self.row_idx, column=0, columnspan=5, sticky="w")
        self.event_listbox.bind("<Double-1>", self.move_to_event)

        scrollbar = tk.Scrollbar(self.frame, orient="vertical", width=20)
        self.event_listbox.config(yscrollcommand = scrollbar.set)
        scrollbar.config(command=self.event_listbox.yview)
        scrollbar.grid(row=self.row_idx, column=3, sticky="ns")
        self.row_idx += 1

        self.event_count_frame = tk.Frame(self.frame,
                                          bd=0,
                                          relief=tk.FLAT,
                                          padx=8,
                                          pady=6)
        self.event_count_frame.grid(row=self.row_idx, column=0, columnspan=5,
                                    sticky="ew", pady=(4, 0))
        self.event_count_frame.grid_columnconfigure(0, weight=1)
        summary_label = tk.Label(self.event_count_frame,
                                 text="Event summary",
                                 font=("Arial", TEXT_SIZE, "bold"),
                                 anchor="w",
                                 fg="#444444")
        summary_label.grid(row=0, column=0, sticky="w", pady=(0, 6))
        event_count_rows = [
            ("Assigned", "assigned"),
            ("E-Finished", "errand_finished"),
            ("T-Finished", "task_finished"),
        ]
        for row_idx, (label_text, event_type) in enumerate(event_count_rows, start=1):
            row_frame = tk.Frame(self.event_count_frame)
            row_frame.grid(row=row_idx, column=0, sticky="ew",
                           pady=(0, 2 if row_idx < len(event_count_rows) else 0))
            row_frame.grid_columnconfigure(1, weight=1)

            count_label = tk.Label(row_frame,
                                   text=f"{label_text}:",
                                   font=("Arial", TEXT_SIZE),
                                   anchor="w",
                                   fg="#2b2f36")
            count_label.grid(row=0, column=0, sticky="w")

            count_value = tk.Label(row_frame,
                                   text="0",
                                   font=("Arial", TEXT_SIZE + 1, "bold"),
                                   anchor="e",
                                   width=6,
                                   fg="#222222")
            count_value.grid(row=0, column=1, sticky="e", padx=(12, 0))
            self.event_count_value_labels[event_type] = count_value
        self.row_idx += 1

        self.init_event_count_tracker()
        print("Done!")

        self.show_grid()
        self.show_static_loc()
        self.show_tasks()
        self.mark_conf_agents()

        self.new_time.set(self.pcf.start_tstep)
        self.max_event_t = 0
        self.update_curtime()

        self.sync_viewport_with_panel_width()
        self.resume_zoom()

        self.frame.update()  # Adjust window size
        if self.pcf.use_viewport_mode:
            wd_width = self.pcf.viewport_width_px + self.frame.winfo_width() + 6
            wd_height = max(self.pcf.viewport_height_px, self.frame.winfo_height()) + 5
        else:
            # Use width and height for scaling
            wd_width = min((self.pcf.width+1) * self.pcf.tile_size + 2,
                           self.pcf.window.winfo_screenwidth())
            wd_height = (self.pcf.height+1) * self.pcf.tile_size + 1
            if self.gui_column == 1:
                wd_width += self.frame.winfo_width() + 3
                wd_height = max(wd_height, self.frame.winfo_height()) + 5
        self.pcf.window.geometry(f"{wd_width}x{wd_height}")
        self.pcf.window.title("PlanViz")
        if self.pcf.use_viewport_mode:
            self.pcf.window.update_idletasks()
            self.center_view_on_initial_focus()
            self.update_minimap_viewport()


    def on_canvas_configure(self, _):
        self.update_minimap_viewport()


    def sync_viewport_with_panel_width(self) -> None:
        if not self.pcf.use_viewport_mode:
            return

        self.frame.update_idletasks()
        measured_panel_width = max(self.frame.winfo_width(), 0)
        if measured_panel_width <= 0:
            return

        self.pcf.panel_width_px = measured_panel_width
        self.pcf.default_tile_size = max(
            self.pcf.ppm * self.pcf.moves,
            self.pcf.compute_default_tile_size(),
        )


    def get_visible_world_bbox(self) -> Tuple[float, float, float, float]:
        x0, x1 = self.pcf.canvas.xview()
        y0, y1 = self.pcf.canvas.yview()
        left = x0 * self.pcf.world_width_px
        right = x1 * self.pcf.world_width_px
        top = y0 * self.pcf.world_height_px
        bottom = y1 * self.pcf.world_height_px
        return (left, top, right, bottom)


    def update_minimap_viewport(self):
        if not self.pcf.use_viewport_mode or self.minimap_canvas is None or \
            self.minimap_view_obj is None:
            return

        self.pcf.update_world_view_metrics()
        left, top, right, bottom = self.get_visible_world_bbox()
        self.minimap_canvas.coords(self.minimap_view_obj,
                                   self.pcf.minimap_offset_x_px + left * self.pcf.minimap_scale,
                                   self.pcf.minimap_offset_y_px + top * self.pcf.minimap_scale,
                                   self.pcf.minimap_offset_x_px + right * self.pcf.minimap_scale,
                                   self.pcf.minimap_offset_y_px + bottom * self.pcf.minimap_scale)


    def center_view_on_world(self, center_x:float, center_y:float):
        if not self.pcf.use_viewport_mode:
            return

        self.pcf.update_world_view_metrics()
        x0, x1 = self.pcf.canvas.xview()
        y0, y1 = self.pcf.canvas.yview()
        visible_width = max((x1 - x0) * self.pcf.world_width_px, 1.0)
        visible_height = max((y1 - y0) * self.pcf.world_height_px, 1.0)

        left = max(0.0, min(center_x - visible_width / 2.0,
                            self.pcf.world_width_px - visible_width))
        top = max(0.0, min(center_y - visible_height / 2.0,
                           self.pcf.world_height_px - visible_height))

        self.pcf.canvas.xview_moveto(left / self.pcf.world_width_px)
        self.pcf.canvas.yview_moveto(top / self.pcf.world_height_px)
        self.update_minimap_viewport()


    def center_view_on_initial_focus(self):
        if not self.pcf.use_viewport_mode or self.pcf.initial_focus_bbox is None:
            return

        min_row, max_row, min_col, max_col = self.pcf.initial_focus_bbox
        center_x = ((min_col + max_col + 1) / 2.0) * self.pcf.tile_size
        center_y = ((min_row + max_row + 1) / 2.0) * self.pcf.tile_size
        self.center_view_on_world(center_x, center_y)


    def move_view_from_minimap_event(self, event):
        if not self.pcf.use_viewport_mode:
            return

        local_x = event.x - self.pcf.minimap_offset_x_px
        local_y = event.y - self.pcf.minimap_offset_y_px
        world_x = min(max(local_x / self.pcf.minimap_scale, 0), self.pcf.world_width_px)
        world_y = min(max(local_y / self.pcf.minimap_scale, 0), self.pcf.world_height_px)
        self.center_view_on_world(world_x, world_y)


    def on_minimap_press(self, event):
        self.minimap_dragging = True
        self.move_view_from_minimap_event(event)


    def on_minimap_drag(self, event):
        if not self.minimap_dragging:
            return
        self.move_view_from_minimap_event(event)


    def on_minimap_release(self, event):
        if self.minimap_dragging:
            self.move_view_from_minimap_event(event)
        self.minimap_dragging = False

    def init_color_legend(self) -> None:
        legend_label = tk.Label(self.frame, text="Agent colors", font=("Arial", TEXT_SIZE))
        legend_label.grid(row=self.row_idx, column=0, columnspan=3, sticky="w")
        self.row_idx += 1

        legend_frame = tk.Frame(self.frame)
        legend_frame.grid(row=self.row_idx, column=0, columnspan=6, sticky="w")
        legend_items = [
            ("Normal", AGENT_COLORS[AgentStatus.NORMAL.color_key]),
            ("Delayed", AGENT_COLORS[AgentStatus.DELAYED.color_key]),
            ("Errand reached", AGENT_COLORS[AgentStatus.ERRAND_FINISHED.color_key]),
            ("Error", AGENT_COLORS["collide"]),
        ]
        for item_idx, (label_text, color) in enumerate(legend_items):
            item_frame = tk.Frame(legend_frame)
            item_frame.grid(row=0, column=item_idx, sticky="w", padx=(0, 12))
            color_box = self.create_agent_legend_icon(item_frame, color)
            color_box.pack(side=tk.LEFT, padx=(2, 6), pady=1)
            color_label = tk.Label(item_frame, text=label_text, font=("Arial", TEXT_SIZE))
            color_label.pack(side=tk.LEFT, pady=1)
        self.row_idx += 1

    def create_agent_legend_icon(self, parent:tk.Widget, color:str) -> tk.Canvas:
        marker_size = 28
        marker_canvas = tk.Canvas(parent,
                                  width=marker_size,
                                  height=marker_size,
                                  highlightthickness=0,
                                  bd=0,
                                  bg=parent.cget("bg"))

        offset = 0.05
        marker_canvas.create_oval(offset * marker_size,
                                  offset * marker_size,
                                  (1 - offset) * marker_size,
                                  (1 - offset) * marker_size,
                                  fill=color,
                                  outline="")

        if self.pcf.agent_model == "MAPF_T":
            dir_loc = get_dir_loc((0, 0, 0))
            marker_canvas.create_oval(dir_loc[0] * marker_size,
                                      dir_loc[1] * marker_size,
                                      dir_loc[2] * marker_size,
                                      dir_loc[3] * marker_size,
                                      fill="navy",
                                      outline="")
        return marker_canvas

    def init_event_count_tracker(self) -> None:
        self.event_count_times = []
        self.event_count_prefix = {
            "assigned": [],
            "errand_finished": [],
            "task_finished": [],
        }
        if self.pcf.max_seq_num <= 0:
            return

        event_count_by_time:Dict[int, Dict[str, int]] = {}

        def add_event_count(tstep:int, event_type:str) -> None:
            if tstep not in event_count_by_time:
                event_count_by_time[tstep] = {
                    "assigned": 0,
                    "errand_finished": 0,
                    "task_finished": 0,
                }
            event_count_by_time[tstep][event_type] += 1

        for tstep, cur_events in self.pcf.events["assigned"].items():
            for global_task_id in cur_events:
                if global_task_id % self.pcf.max_seq_num == 0:
                    add_event_count(tstep, "assigned")

        for tstep, cur_events in self.pcf.events["finished"].items():
            for global_task_id in cur_events:
                task_id = global_task_id // self.pcf.max_seq_num
                seq_id = global_task_id % self.pcf.max_seq_num
                last_seq_id = len(self.pcf.seq_tasks[task_id].tasks) - 1
                if seq_id == last_seq_id:
                    add_event_count(tstep, "task_finished")
                else:
                    add_event_count(tstep, "errand_finished")

        running_total = {
            "assigned": 0,
            "errand_finished": 0,
            "task_finished": 0,
        }
        for tstep in sorted(event_count_by_time.keys()):
            for event_type in running_total:
                running_total[event_type] += event_count_by_time[tstep][event_type]
            self.event_count_times.append(tstep)
            for event_type in running_total:
                self.event_count_prefix[event_type].append(running_total[event_type])

    def get_event_count_breakdown(self, end_tstep:int) -> Dict[str, int]:
        zero_breakdown = {
            "assigned": 0,
            "errand_finished": 0,
            "task_finished": 0,
        }
        if not self.event_count_times:
            return zero_breakdown

        event_idx = bisect_right(self.event_count_times, end_tstep) - 1
        if event_idx < 0:
            return zero_breakdown

        return {
            "assigned": self.event_count_prefix["assigned"][event_idx],
            "errand_finished": self.event_count_prefix["errand_finished"][event_idx],
            "task_finished": self.event_count_prefix["task_finished"][event_idx],
        }

    def update_event_count_label(self, end_tstep:int, is_main_event_list:bool) -> None:
        if not is_main_event_list or self.event_count_frame is None or \
            (not self.event_count_frame.winfo_exists()):
            return

        event_breakdown = self.get_event_count_breakdown(end_tstep)
        for event_type, count_value in event_breakdown.items():
            if event_type not in self.event_count_value_labels:
                continue
            self.event_count_value_labels[event_type].config(text=str(count_value))

    def set_error_listbox_height(self, error_count: int) -> None:
        min_rows = 2
        max_visible_errors = 12
        max_rows = max(min_rows, max_visible_errors + 2)
        total_rows = max(min_rows, min(error_count + 2, max_rows))
        self.conflict_listbox.config(height=total_rows)

    def update_error_list(self, error_listbox):
        if error_listbox == None:
            return
        end_tstep = self.pcf.cur_tstep
        conf_id = 0
        shown_conflict_count = 0
        error_listbox.delete(0, tk.END)
        selected_conflicts = {
            conf_str for conf_str, conf in self.shown_conflicts.items() if conf[1]
        }
        self.shown_conflicts = {}
        error_listbox.config(font=self.listbox_monospace_font)
        header = f"{'Time':<6}{'a1':<5}{'a2':<5}{'Event':<12}"
        error_listbox.insert(conf_id, header)
        conf_id += 1
        error_listbox.insert(conf_id, "-" * 34)  # Separator line
        conf_id += 1
        if self.pcf.event_limit == 0:
            self.set_error_listbox_height(0)
            return
        # [task_id, robot1, robot2, timestep, description]
        for tstep in sorted(
            (cur_tstep for cur_tstep in self.pcf.conflicts.keys() if cur_tstep <= end_tstep),
            reverse=True
        ):
            if tstep < self.pcf.start_tstep:
                continue
            if tstep > self.pcf.end_tstep:
                break

            for conf in self.pcf.conflicts[tstep]:
                if len(conf) == 5:
                    task_id, agent1, agent2, tstep_std, description = conf
                if len(conf) == 4:
                    agent1, agent2, tstep_std, description = conf
                if agent1 > (self.pcf.team_size-1) or agent2 > (self.pcf.team_size-1):
                    continue
                assert tstep == tstep_std
                pid = tstep - self.pcf.start_tstep
                conf_str = f"{tstep:<6}{agent1:<5}{agent2:<5}"
                if description == "vertex conflict":
                    _loc = "("+ str(self.pcf.agents[agent1].plan_path[pid][0]) + "," +\
                        str(self.pcf.agents[agent1].plan_path[pid][1]) +")"
                    conf_str += "v: " + _loc
                elif description == "edge conflict":
                    _loc1 = "(" + str(self.pcf.agents[agent1].plan_path[pid-1][0]) + "," +\
                        str(self.pcf.agents[agent1].plan_path[pid-1][1]) + ")"
                    _loc2 = "(" + str(self.pcf.agents[agent1].plan_path[pid-1][0]) + "," +\
                        str(self.pcf.agents[agent1].plan_path[pid-1][1]) + ")"
                    conf_str += "e: " + _loc1 + "->" + _loc2
                elif description == "incorrect vector size":
                    conf_str += "Planner timeout"
                elif "already assigned" in description:
                    conf_str += f"T({task_id}) !-> a1 "
                else:
                    conf_str += description
                self.conflict_listbox.insert(conf_id, conf_str)
                if tstep == self.pcf.cur_tstep:
                    self.conflict_listbox.itemconfigure(conf_id, background='yellow')
                self.shown_conflicts[conf_str] = [conf, conf_str in selected_conflicts]
                conf_id += 1
                shown_conflict_count += 1
                if shown_conflict_count >= self.pcf.event_limit:
                    self.set_error_listbox_height(shown_conflict_count)
                    return
        self.set_error_listbox_height(shown_conflict_count)

    def set_event_listbox_height(self, event_listbox, event_count: int) -> None:
        if event_listbox == None or (not event_listbox.winfo_exists()):
            return

        min_rows = 2
        max_visible_events = 20
        max_rows = max(min_rows, max_visible_events + 2)
        total_rows = max(min_rows, min(event_count + 2, max_rows))
        event_listbox.config(height=total_rows)

        
    
    def update_event_list(self, event_listbox, pop):
        if event_listbox == None or (not event_listbox.winfo_exists()):
            return
        self.max_event_t = max(self.pcf.cur_tstep, self.max_event_t)
        end_tstep = self.pcf.cur_tstep
        is_main_event_list = event_listbox == self.event_listbox

        self.shown_events:Dict[str, Tuple[int,int,int,int,str]] = {}
        self.eve_id = 0
        event_listbox.delete(0, tk.END)
        event_listbox.config(font=self.listbox_monospace_font)
        header = f"{'Time':<6}{'Agent':<8}{'Event':<12}{'Task ID':<8}"
        event_listbox.insert(self.eve_id, header)
        self.eve_id += 1
        event_listbox.insert(self.eve_id, "-" * 34)  # Separator line
        self.eve_id += 1
        shown_event_count = 0
        time_list = list(self.pcf.events["assigned"])
        time_list.extend(x for x in self.pcf.events["finished"] if x not in time_list)
        time_list = sorted((tstep for tstep in time_list if tstep <= end_tstep), reverse=True)
        if self.pcf.event_limit == 0:
            self.set_event_listbox_height(event_listbox, 0)
            self.update_event_count_label(end_tstep, is_main_event_list)
            return
        for tstep in time_list:
            if tstep in self.pcf.events["assigned"]:
                cur_events= self.pcf.events["assigned"][tstep]
                for global_task_id in sorted(cur_events.keys(), reverse=False):
                    task_id = global_task_id // self.pcf.max_seq_num
                    seq_id = global_task_id % self.pcf.max_seq_num
                    ag_id = cur_events[global_task_id]
                    if pop and \
                       (ag_id != self.right_click_agent): 
                        continue
                    if seq_id == 0:
                        e_str = f"{tstep:<6}{ag_id:<8}{'Assigned':<12}{task_id:<8}"
                        self.shown_events[e_str] = (tstep, ag_id, task_id, seq_id, "assigned")
                        event_listbox.insert(self.eve_id, e_str)
                        if tstep == self.pcf.cur_tstep:
                            event_listbox.itemconfigure(self.eve_id, background='yellow')
                            
                        self.eve_id += 1
                        shown_event_count += 1
                        if shown_event_count >= self.pcf.event_limit:
                            self.set_event_listbox_height(event_listbox, shown_event_count)
                            self.update_event_count_label(end_tstep, is_main_event_list)
                            return
            if tstep in self.pcf.events["finished"]:
                cur_events = self.pcf.events["finished"][tstep]
                for global_task_id in sorted(cur_events.keys(), reverse=False):
                    task_id = global_task_id // self.pcf.max_seq_num
                    if pop and self.right_click_agent < 0 and not (task_id in self.right_click_all_tasks_idx): continue
                    seq_id = global_task_id % self.pcf.max_seq_num
                    ag_id = cur_events[global_task_id]
                    if pop and (self.right_click_agent > -1 and ag_id != self.right_click_agent): continue
                    if seq_id == len(self.pcf.seq_tasks[task_id].tasks) - 1:
                        e_str = f"{tstep:<6}{ag_id:<8}{'T-Finished':<12}{task_id:<8}"
                        self.shown_events[e_str] = (tstep, ag_id, task_id, seq_id, "task_finished")
                    else:
                        e_str = f"{tstep:<6}{ag_id:<8}{'E-Finished':<12}{task_id:<8}"
                        self.shown_events[e_str] = (tstep, ag_id, task_id, seq_id, "errand_finished")
                        
                    event_listbox.insert(self.eve_id, e_str)
                    if tstep == self.pcf.cur_tstep:
                            event_listbox.itemconfigure(self.eve_id, background='yellow')
                    self.eve_id += 1
                    shown_event_count += 1
                    if shown_event_count >= self.pcf.event_limit:
                        self.set_event_listbox_height(event_listbox, shown_event_count)
                        self.update_event_count_label(end_tstep, is_main_event_list)
                        return
        self.set_event_listbox_height(event_listbox, shown_event_count)
        self.update_event_count_label(end_tstep, is_main_event_list)
            

    def update_location_event_list(self, event_listbox):
        """Update location event list to show task-related events"""
        if event_listbox == None or (not event_listbox.winfo_exists()):
            return
        
        self.max_event_t = max(self.pcf.cur_tstep, self.max_event_t)
        end_tstep = self.max_event_t
        
        # Clear and refill the location event listbox
        event_listbox.delete(0, tk.END)
        event_listbox.config(font=self.listbox_monospace_font)
        
        # Add header in the same format as update_event_list
        header = f"{'Time':<6}{'Agent':<8}{'Event':<12}{'Task ID':<8}"
        event_listbox.insert(0, header)
        event_listbox.insert(1, "-" * 34)  # Separator line
        eve_id = 2
        shown_event_count = 0
        
        # Similar to update_event_list, iterate through timesteps and events
        time_list = list(self.pcf.events["assigned"])
        time_list.extend(x for x in self.pcf.events["finished"] if x not in time_list)
        time_list = sorted(time_list, reverse=False)
        
        for tstep in range(end_tstep, -1, -1):
            # Check assignment events
            if tstep in self.pcf.events["assigned"]:
                cur_events = self.pcf.events["assigned"][tstep]
                for global_task_id in sorted(cur_events.keys(), reverse=False):
                    task_id = global_task_id // self.pcf.max_seq_num
                    seq_id = global_task_id % self.pcf.max_seq_num
                    ag_id = cur_events[global_task_id]
                    
                    # Check if task is in the selected task list
                    if (not (task_id in self.right_click_all_tasks_idx)): 
                        continue
                    if seq_id == 0:
                        e_str = f"{tstep:<6}{ag_id:<8}{'Assigned':<12}{task_id:<8}"
                        event_listbox.insert(eve_id, e_str)
                        if tstep == self.pcf.cur_tstep:
                            event_listbox.itemconfigure(eve_id, background='yellow')
                        eve_id += 1
                        shown_event_count += 1
        self.set_event_listbox_height(event_listbox, shown_event_count)

    def change_task_color(self, task_id:int, seq_id:int, color:str) -> None:
        """ Change the color of the task

        Args:
            task_id (int): the index in self.pcf.seq_tasks
            color   (str): the color to be changed
        """
        # Lazy render if not yet rendered
        self.pcf.lazy_render_task(task_id, seq_id)

        # Change the color of the task
        cur_task_obj = self.pcf.seq_tasks[task_id].tasks[seq_id].task_obj.obj
        if self.pcf.canvas.itemcget(cur_task_obj, "fill") != color:
            self.pcf.canvas.itemconfig(cur_task_obj, fill=color)
        # return cur_task_obj

    def select_conflict(self, event):
        selected_indices = event.widget.curselection()  # Get all selected indices

        for conf in self.shown_conflicts.values():  # Reset all the conflicts to non-selected
            conf[1] = False

        for _sid_ in selected_indices:  # Mark the selected conflicting agents to red
            conf_str = self.conflict_listbox.get(_sid_)
            if conf_str not in self.shown_conflicts:
                continue
            self.shown_conflicts[conf_str][1] = True

        self.update_agent_colors()


    def restart_timestep(self):
        self.new_time.set(self.pcf.start_tstep)
        for ag_idx in self.pcf.shown_path_agents:
            for arrow_id in self.pcf.agent_shown_task_arrow[ag_idx]:
                self.pcf.canvas.delete(arrow_id)
            self.pcf.agent_shown_task_arrow[ag_idx] = []
            for _p_ in self.pcf.agents[ag_idx].path_objs:
                self.pcf.canvas.itemconfigure(_p_.obj, state=tk.HIDDEN)
        self.pcf.shown_path_agents.clear()
        self.pcf.shown_tasks_seq.clear()
        
        self.pcf.event_tracker["aid"] = 0
        self.pcf.event_tracker["fid"] = 0

        # Hide all the tasks
        for task_id, seq_task in self.pcf.seq_tasks.items():
            for seq_id, task in enumerate(seq_task.tasks):
                task.state = "unassigned"
                self.hide_single_task(task_id, seq_id)

        self.max_event_t = 0
        self.update_curtime()
        


    def on_hover(self, event):
        x_adjusted = self.pcf.canvas.canvasx(event.x)
        y_adjusted = self.pcf.canvas.canvasy(event.y)
        grid_x = int(x_adjusted // self.pcf.tile_size)
        grid_y = int(y_adjusted // self.pcf.tile_size)
        
        if 0 <= grid_x < self.pcf.width and 0 <= grid_y < self.pcf.height:
            self.mouse_loc_label.config(text=f"Mouse Position: ({grid_x}, {grid_y})")
            self.pcf.canvas.delete("hover_text")
            if self.show_hover_loc.get():
                self.pcf.canvas.create_text((grid_x + 0.5) * self.pcf.tile_size, 
                                        (grid_y + 0.5) * self.pcf.tile_size, 
                                        text=f"({grid_x}, {grid_y})", 
                                        fill="red", tags="hover_text", font=("Arial", TEXT_SIZE))


    def move_to_conflict(self, event):
        if self.is_run.get() is True:
            return

        _sid_ = event.widget.curselection()  # get all selected indices
        if len(_sid_) < 1:
            return
        _sid_ = _sid_[0]
        conf = self.shown_conflicts[self.conflict_listbox.get(_sid_)]
        if len(conf[0]) == 5:
            task_id, agent1, agent2, tstep_std, description = conf[0]
        if len(conf[0]) == 4:
            agent1, agent2, tstep_std, description = conf[0]    
        self.shown_conflicts[self.conflict_listbox.get(_sid_)][1] = True
        self.new_time.set(int(tstep_std)-1)
        self.update_curtime()


    def move_to_event(self, event):
        if self.is_run.get() is True:
            return
        selected_idx = event.widget.curselection()  # get all selected indices
        if len(selected_idx) < 1:
            return 
        selected_idx = selected_idx[0]
        
        # Determine which event listbox triggered the event
        widget = event.widget
        eve_str = None
        
        if widget == self.pop_location_listbox:
            # Get event from location event listbox
            eve_str = self.pop_location_listbox.get(selected_idx)
            # Check if it's a header row or separator line
            if "------" in eve_str or "Time" in eve_str or "No events found" in eve_str:
                return
            # Parse location event string, format: "123   1      Assigned   5"
            parts = eve_str.split()
            if len(parts) >= 4:
                try:
                    tstep = int(parts[0])
                    ag_idx = int(parts[1])
                    self.clear_agent_selection()
                    self.new_time.set(tstep)
                    self.update_curtime()
                    first_errand_t = self.show_colorful_errands(ag_idx)
                    if first_errand_t != -1:
                        self.show_ag_plan(ag_idx, first_errand_t)
                    return
                except (ValueError, IndexError):
                    return
            else:
                return
                
        elif self.right_click_status == "right":
            eve_str = self.pop_event_listbox.get(selected_idx)
        else:
            eve_str = self.event_listbox.get(selected_idx)
            
        if "------" in eve_str: 
            return
        if eve_str not in self.shown_events:
            return
            
        cur_eve:Tuple[int,int,int,int,str] = self.shown_events[eve_str] #  (tstep, ag_id, task_id, seq_id, status)
        new_t = max(cur_eve[0], 0)  # move to one timestep ahead the event
        self.clear_agent_selection()
        self.new_time.set(new_t)
        self.update_curtime()
        ag_idx = cur_eve[1]
        first_errand_t = self.show_colorful_errands(ag_idx)
        if first_errand_t != -1:
            self.show_ag_plan(ag_idx, first_errand_t)
        
    def check_left_click(self, event):
        self.last_click_pos = (event.x, event.y)
        self.dragging = False  # Not actually dragging yet
        # Do not immediately handle single-click logic; wait to see if the user drags or clicks again
        # However, call canvas.scan_mark(...) to prepare for a potential drag
        self.pcf.canvas.scan_mark(event.x, event.y)

    def on_mouse_drag(self, event):
        # If the mouse moves more than a certain distance, we consider it a drag
        if not self.dragging:
            dx = event.x - self.last_click_pos[0]
            dy = event.y - self.last_click_pos[1]
            dist = math.hypot(dx, dy)
            if dist > self.drag_move_threshold:
                self.dragging = True

        if self.dragging:
            self.pcf.canvas.scan_dragto(event.x, event.y, gain=1)
            self.update_minimap_viewport()

    def on_button_release(self, event):
        # If you haven't dragged when you release it, and it doesn't trigger a double click, it will be treated as a single click.
        if not self.dragging:
            self.left_click(event)

    def __wheel(self, event):
        """ Zoom with mouse wheel
        """
        scale = 1.0
        # Respond to Linux (event.num) or Windows (event.delta) wheel event
        if event.num == 5 or event.delta < 0:  # scroll down, smaller
            threshold = round(min(self.pcf.width, self.pcf.height) * self.pcf.tile_size)
            if threshold < 30:
                return  # image is less than 30 pixels
            scale /= 1.05
            self.pcf.tile_size /= 1.05
        if event.num == 4 or event.delta > 0:  # scroll up, bigger
            scale *= 1.05
            self.pcf.tile_size *= 1.05
        self.pcf.canvas.scale("all", 0, 0, scale, scale)  # rescale all objects
        for child_widget in self.pcf.canvas.find_withtag("text"):
            self.pcf.canvas.itemconfigure(child_widget,
                                          font=("Arial", int(self.pcf.tile_size // 2)))
        for child_widget in self.pcf.canvas.find_withtag("hwy"):
            self.pcf.canvas.itemconfigure(child_widget,
                                          font=("Arial", int(self.pcf.tile_size*1.2)))
        self.pcf.update_canvas_scrollregion()
        self.update_minimap_viewport()


    def resume_zoom(self):
        base_tile_size = self.pcf.default_tile_size
        if base_tile_size < 1:
            base_tile_size = self.pcf.ppm * self.pcf.moves
        __scale = base_tile_size / self.pcf.tile_size
        self.pcf.canvas.scale("all", 0, 0, __scale, __scale)
        self.pcf.tile_size = base_tile_size
        self.pcf.update_viewport_metrics()
        self.pcf.canvas.configure(width=self.pcf.viewport_width_px,
                                  height=self.pcf.viewport_height_px)
        for child_widget in self.pcf.canvas.find_withtag("text"):
            self.pcf.canvas.itemconfigure(child_widget,
                                          font=("Arial", int(self.pcf.tile_size // 2)))
        for child_widget in self.pcf.canvas.find_withtag("hwy"):
            self.pcf.canvas.itemconfigure(child_widget,
                                          font=("Arial", int(self.pcf.tile_size*1.2)))
        self.pcf.update_canvas_scrollregion()
        self.update_minimap_viewport()
        self.pcf.canvas.update()

    def clear_agent_selection(self, moving=False):
        for ag_idx in self.pcf.shown_path_agents:
            for task_idx in self.pcf.shown_tasks_seq:
                for arrow_id in self.pcf.agent_shown_task_arrow[ag_idx]:
                    self.pcf.canvas.delete(arrow_id)
                for idx, tsk in enumerate(self.pcf.seq_tasks[task_idx].tasks):
                    self.hide_single_task(task_idx, idx)
            for _p_ in self.pcf.agents[ag_idx].path_objs:
                self.pcf.canvas.itemconfigure(_p_.obj, state=tk.HIDDEN)
                self.pcf.canvas.tag_lower(_p_.obj)
        if not moving:
            self.pcf.shown_tasks_seq.clear()
            self.pcf.shown_path_agents.clear()
            self.new_time.set(self.pcf.cur_tstep)
            self.update_curtime()

    def left_click(self, event):
        self.right_click_status = "left"
        if not (self.pop_gui_window is None) and self.pop_gui_window.winfo_exists() != 0:
            self.pop_gui_window.destroy()
        
        # Check for agents and tasks at click location for popup
        x_adjusted = self.pcf.canvas.canvasx(event.x)
        y_adjusted = self.pcf.canvas.canvasy(event.y)
        grid_column = int(x_adjusted // self.pcf.tile_size)
        grid_row = int(y_adjusted // self.pcf.tile_size)
        grid_loc = [grid_column, grid_row]
        items = self.pcf.canvas.find_overlapping(x_adjusted-0.1, y_adjusted-0.1, 
                                                 x_adjusted+0.1, y_adjusted+0.1)
        
        ag_idx = self.get_ag_idx(event)
        show_popup = False
        
        # Check if there are tasks at this location
        task_items = []
        for item in items:
            if item in self.pcf.grid2task.keys():
                task_items.extend(self.pcf.grid2task[item])
        
        # Show popup if there are agents or tasks at this location
        if ag_idx != -1 or len(task_items) > 0:
            show_popup = True
            self.right_click_agent = ag_idx
            self.right_click_all_tasks_idx = task_items
            self.create_pop_window(grid_loc)
            self.update_event_list(self.pop_event_listbox, 1)
            self.update_location_event_list(self.pop_location_listbox)
        
        # Original agent selection logic
        if ag_idx == -1 and self.run_button['state'] == tk.NORMAL:
            self.clear_agent_selection()
        if ag_idx != -1:
            first_errand_t = self.show_colorful_errands(ag_idx)
            if first_errand_t != -1:
                self.show_ag_plan(ag_idx, first_errand_t)

            

    def create_pop_window(self, grid_loc):
        if self.pop_gui_window == None or self.pop_gui_window.winfo_exists() == 0:       
            mouse_x = self.pcf.window.winfo_pointerx()
            mouse_y = self.pcf.window.winfo_pointery()
            offset_x = 20  
            offset_y = 20 
            window_x = mouse_x + offset_x
            window_y = mouse_y + offset_y
            
            self.pop_gui_window = tk.Toplevel()
            self.pop_gui_window.title(f"Event List - Location ({grid_loc[0]}, {grid_loc[1]})")
            self.pop_gui_window.transient(self.pcf.window)
            self.pop_gui_window.lift()
            width = 300  # Width to accommodate two lists
            height = int(8 * self.pcf.tile_size)  # Increase height
            
            self.pop_gui_window.geometry(f"{width}x{height}+{window_x}+{window_y}")
            self.pop_frame = tk.Frame(self.pop_gui_window)
            self.pop_frame.grid(row=0, column=0, sticky="nsew")
            
            # Configure grid weights for proper component scaling
            self.pop_gui_window.grid_rowconfigure(0, weight=1)
            self.pop_gui_window.grid_columnconfigure(0, weight=1)
            self.pop_frame.grid_rowconfigure(1, weight=1)
            self.pop_frame.grid_rowconfigure(3, weight=1)
            self.pop_frame.grid_columnconfigure(0, weight=1)
            self.pop_frame.grid_columnconfigure(1, weight=1)
            
            # First event list - agent events
            agent_label = tk.Label(self.pop_frame, text="Agent Events at this Location", font=("Arial", TEXT_SIZE))
            agent_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=5)
            
            self.pop_event_listbox = tk.Listbox(self.pop_frame,
                                width=35,
                                height=9,
                                font=("Arial",TEXT_SIZE),
                                selectmode=tk.EXTENDED)
            self.pop_event_listbox.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5)
            self.pop_event_listbox.bind("<Double-1>", self.move_to_event)
            
            agent_scrollbar = tk.Scrollbar(self.pop_frame, orient="vertical", width=20)
            self.pop_event_listbox.config(yscrollcommand = agent_scrollbar.set)
            agent_scrollbar.config(command=self.pop_event_listbox.yview)
            agent_scrollbar.grid(row=1, column=2, sticky="ns")
            
            # Second event list - location events  
            location_label = tk.Label(self.pop_frame, text="Tasks at this Location", font=("Arial", TEXT_SIZE))
            location_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=(10,5))
            
            # Create second event listbox
            self.pop_location_listbox = tk.Listbox(self.pop_frame,
                                width=35,
                                height=9,
                                font=("Arial",TEXT_SIZE),
                                selectmode=tk.EXTENDED)
            self.pop_location_listbox.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=5, pady=(0,5))
            self.pop_location_listbox.bind("<Double-1>", self.move_to_event)
            
            location_scrollbar = tk.Scrollbar(self.pop_frame, orient="vertical", width=20)
            self.pop_location_listbox.config(yscrollcommand = location_scrollbar.set)
            location_scrollbar.config(command=self.pop_location_listbox.yview)
            location_scrollbar.grid(row=3, column=2, sticky="ns")
            
        else:
            # If window already exists, just update the title
            self.pop_gui_window.title(f"Event List - Location ({grid_loc[0]}, {grid_loc[1]})")

    def right_click(self, event):
        x_adjusted = self.pcf.canvas.canvasx(event.x)
        y_adjusted = self.pcf.canvas.canvasy(event.y)
        grid_column = int(x_adjusted // self.pcf.tile_size)
        grid_row = int(y_adjusted // self.pcf.tile_size)
        grid_loc = [grid_column, grid_row]
        items = self.pcf.canvas.find_overlapping(x_adjusted-0.1, y_adjusted-0.1, 
                                                 x_adjusted+0.1, y_adjusted+0.1)
        
        ag_idx = self.get_ag_idx(event)
        self.right_click_agent = ag_idx
        if ag_idx != -1:
            self.right_click_status = "right"
        
        self.right_click_all_tasks_idx = []
        for item in items:
            all_tasks_idx = []
            if item in self.pcf.grid2task.keys():
                all_tasks_idx = self.pcf.grid2task[item]
            if len(all_tasks_idx) > 0:
                self.right_click_status = "right"
                self.right_click_all_tasks_idx += all_tasks_idx
        
        if self.right_click_status == "right":
            self.create_pop_window(grid_loc)
            # Update agent event list (same logic as before)
            self.update_event_list(self.pop_event_listbox, 1)
            # Update location event list (new logic for events at this location)
            self.update_location_event_list(self.pop_location_listbox)
                 

    def get_ag_idx(self, event):
        x_adjusted = self.pcf.canvas.canvasx(event.x)
        y_adjusted = self.pcf.canvas.canvasy(event.y)
        grid_column = int(x_adjusted // self.pcf.tile_size)
        grid_row = int(y_adjusted // self.pcf.tile_size)
        grid_loc = [grid_column, grid_row]
        items = self.pcf.canvas.find_overlapping(x_adjusted-0.1, y_adjusted-0.1, 
                                                 x_adjusted+0.1, y_adjusted+0.1)
        ag_idx = -1
        for item in items:
            tags:Set[str] = self.pcf.canvas.gettags(item)
            is_agent_item = (self.AGENT_OBJ_TAG in tags) or (self.AGENT_TEXT_TAG in tags)
            if not is_agent_item:
                continue
            for tag in tags:
                if tag.isnumeric():
                    ag_idx = int(tag)
                    return ag_idx
                
        return ag_idx


    def show_colorful_errands(self, ag_idx, moving=False):
        agent_tasks = self.pcf.agent_assigned_task[ag_idx]
        agent_tasks = sorted(agent_tasks)
        first_errand = -1
        first_errand_t = -1
        tsk_idx = -1
        for t, i in agent_tasks:
            if self.pcf.cur_tstep >= t-1:
                tsk_idx = i
        if tsk_idx == -1:
            return int(first_errand_t)
        t = []
        for i, task in enumerate(self.pcf.seq_tasks[tsk_idx].tasks):
            task_t = task.events["finished"]["timestep"]
            if task_t == float("inf"):
                task_t = 1e9
            if self.pcf.cur_tstep < task_t:
                first_errand = i
                first_errand_t = task_t
                break
        self.pcf.agent_shown_task_arrow[ag_idx] = self.show_task_seq(ag_idx, tsk_idx, first_errand, moving)
        return int(first_errand_t)


    def show_ag_plan(self, ag_idx, first_errand_t, moving=False):

        self.pcf.lazy_render_agent_path(ag_idx)

        if ag_idx in self.pcf.shown_path_agents and (not moving):  # Remove ag_id if it's already in the set
            self.pcf.shown_path_agents.remove(ag_idx)
            for _p_ in self.pcf.agents[ag_idx].path_objs:
                self.pcf.canvas.itemconfigure(_p_.obj, state=tk.HIDDEN)
                self.pcf.canvas.tag_lower(_p_.obj)
        else:
            self.pcf.shown_path_agents.add(ag_idx)  # Add ag_id to the set
            if not self.show_agent_path.get(): 
                return
            ml = min(first_errand_t+1, len(self.pcf.agents[ag_idx].path_objs))
            for _pid_ in range(self.pcf.cur_tstep+1, ml):
                self.pcf.canvas.itemconfigure(self.pcf.agents[ag_idx].path_objs[_pid_].obj,
                                              state=tk.DISABLED)
                self.pcf.canvas.tag_raise(self.pcf.agents[ag_idx].path_objs[_pid_].obj)
        
        if len(self.pcf.shown_path_agents) == 0:
            self.clear_agent_selection()

    def mark_conf_agents(self) -> None:
        self.conflict_listbox.select_clear(0, self.conflict_listbox.size())
        for conf in self.shown_conflicts.values():
            conf[1] = False
        self.update_agent_colors()


    def off_agent_path(self):
        self.clear_agent_selection(moving=True)
        for ag_idx in self.pcf.shown_path_agents:
            first_errand_t = self.show_colorful_errands(ag_idx, moving=True)
            if first_errand_t != -1:
                self.show_ag_plan(ag_idx, first_errand_t, moving=True)

    def show_task_seq(self, agent_idx, task_idx, first_errand, moving=False):
        def get_center_coords(canvas, item_id):
            # Get the coordinates of the bounding box of the item
            coords = canvas.coords(item_id)
            # Calculate the center
            x_center = (coords[0] + coords[2]) / 2
            y_center = (coords[1] + coords[3]) / 2
            return x_center, y_center
        
        arrows = []
        
        if task_idx in self.pcf.shown_tasks_seq and (not moving):
            self.pcf.shown_tasks_seq.remove(task_idx)
            for arrow_id in self.pcf.agent_shown_task_arrow[agent_idx]:
                self.pcf.canvas.delete(arrow_id)
            for idx, tsk in enumerate(self.pcf.seq_tasks[task_idx].tasks):
                self.hide_single_task(task_idx, idx)
        else:
            self.pcf.shown_tasks_seq.add(task_idx)
            last_obj = self.pcf.agents[agent_idx].agent_obj.obj
            for idx, tsk in enumerate(self.pcf.seq_tasks[task_idx].tasks):
                task_t = tsk.events["finished"]["timestep"]
                if self.pcf.cur_tstep >= task_t:
                    self.change_task_color(task_idx, idx, TASK_COLORS["finished"])
                    continue
                
                self.change_task_color(task_idx,idx, "pink")
                if idx == first_errand:
                    self.change_task_color(task_idx,idx, "orange")

                self.set_task_visibility(task_idx, idx, True)
                x1, y1 = get_center_coords(self.pcf.canvas, last_obj)
                last_obj = tsk.task_obj.obj
                x2, y2 = get_center_coords(self.pcf.canvas, last_obj)
                _arrow = self.pcf.canvas.create_line(x1, y1, x2, y2, arrow=tk.LAST, width=2, fill="#4eb1a6")
                arrows.append(_arrow)

        # Hide tasks that are not in ag_id
        for task_id, seq_task in self.pcf.seq_tasks.items():
            if task_id in self.pcf.shown_tasks_seq:
                for seq_id, tsk in enumerate(seq_task.tasks):
                    task_t = tsk.events["finished"]["timestep"]
                    if self.pcf.cur_tstep >= task_t:
                        continue
                    self.show_single_task(task_id, seq_id, ignore=1)
            else:
                for seq_id in range(len(seq_task.tasks)):
                    self.hide_single_task(task_id, seq_id)
        self.raise_agent_canvas_items()
        return arrows

    def show_grid(self) -> None:
        if self.is_grid.get() is True:
            for _line_ in self.pcf.grids:
                self.pcf.canvas.itemconfig(_line_, state=tk.NORMAL)
        else:
            for _line_ in self.pcf.grids:
                self.pcf.canvas.itemconfig(_line_, state=tk.HIDDEN)


    def show_heat_map(self) -> None:
        if self.is_heat_map.get() is True:
            for item in self.pcf.heat_grids:
                self.pcf.canvas.itemconfig(item.obj, state=tk.DISABLED)
                self.pcf.canvas.itemconfig(item.text, state=tk.DISABLED)
        else:
            for item in self.pcf.heat_grids:
                self.pcf.canvas.itemconfig(item.obj, state=tk.HIDDEN)
                self.pcf.canvas.itemconfig(item.text, state=tk.HIDDEN)


    def show_highway(self) -> None:
        if self.is_highway.get() is True:
            for item in self.pcf.highway:
                self.pcf.canvas.itemconfig(item["obj"], state=tk.DISABLED)
        else:
            for item in self.pcf.highway:
                self.pcf.canvas.itemconfig(item["obj"], state=tk.HIDDEN)


    def show_heuristic_map(self) -> None:
        if self.is_heuristic_map.get() is True:
            for item in self.pcf.heuristic_grids:
                self.pcf.canvas.itemconfig(item.obj, state=tk.DISABLED)
                self.pcf.canvas.itemconfig(item.text, state=tk.DISABLED)
        else:
            for item in self.pcf.heuristic_grids:
                self.pcf.canvas.itemconfig(item.obj, state=tk.HIDDEN)
                self.pcf.canvas.itemconfig(item.text, state=tk.HIDDEN)


    def show_agent_index(self) -> None:
        _state_ = tk.DISABLED if self.show_ag_idx.get() is True else tk.HIDDEN
        _ts_ = tk.DISABLED if (self.show_ag_idx.get() is True and\
            self.show_static.get() is True) else tk.HIDDEN
        self.raise_agent_canvas_items()

        self.pcf.canvas.itemconfig(self.AGENT_TEXT_TAG, state=_state_)
        self.pcf.canvas.itemconfig(self.AGENT_START_TEXT_TAG, state=_ts_)

    def raise_agent_canvas_items(self) -> None:
        self.pcf.canvas.tag_raise(self.AGENT_OBJ_TAG, "all")
        self.pcf.canvas.tag_raise(self.AGENT_DIR_TAG, "all")
        self.pcf.canvas.tag_raise(self.AGENT_START_OBJ_TAG, "all")
        self.pcf.canvas.tag_raise(self.AGENT_TEXT_TAG, "all")
        self.pcf.canvas.tag_raise(self.AGENT_START_TEXT_TAG, "all")

    def set_task_visibility(self, task_id:int, seq_id:int, visible:bool) -> None:
        self.pcf.lazy_render_task(task_id, seq_id)
        task = self.pcf.seq_tasks[task_id].tasks[seq_id]
        box_state = tk.DISABLED if visible else tk.HIDDEN
        text_state = tk.HIDDEN
        if visible and self.show_task_idx.get():
            text_state = tk.DISABLED

        self.pcf.canvas.itemconfig(task.task_obj.obj, state=box_state)
        self.pcf.canvas.itemconfig(task.task_obj.text, state=text_state)
        if self.pcf.grids:
            self.pcf.canvas.tag_lower(task.task_obj.obj, self.pcf.grids[0])

    def show_task_index(self) -> None:
        for (task_id, seq_id) in list(self.pcf.rendered_tasks):
            task = self.pcf.seq_tasks[task_id].tasks[seq_id]
            if task.task_obj is None:
                continue
            obj_state = self.pcf.canvas.itemcget(task.task_obj.obj, "state")
            self.set_task_visibility(task_id, seq_id, obj_state != tk.HIDDEN)
        self.raise_agent_canvas_items()


    def show_tasks(self) -> None:
        for (task_id, seq_id) in list(self.pcf.rendered_tasks):
            self.hide_single_task(task_id, seq_id)
        mode = self.task_shown.get()
        if mode == "none":
            self.show_task_index()
            return
        elif mode == "All Tasks":
            for (task_id, seq_task) in self.pcf.seq_tasks.items():
                for i, task in enumerate(seq_task.tasks):
                    self.set_task_visibility(task_id, i, True)

        elif mode == "Next Errand":
            for ag_id in range(self.pcf.team_size):
                if ag_id not in self.pcf.agent_assigned_task:
                    continue
                current_task_id = None
                for assign_t, task_id in self.pcf.agent_assigned_task[ag_id]:
                    if assign_t <= self.pcf.cur_tstep:
                        current_task_id = task_id

                if current_task_id is None:
                    continue

                seq_task = self.pcf.seq_tasks[current_task_id]
                for i, task in enumerate(seq_task.tasks):
                    task_t = task.events["finished"]["timestep"]
                    if task.state in ["assigned", "newlyassigned"] and task_t > self.pcf.cur_tstep:
                        self.set_task_visibility(current_task_id, i, True)
                        break

        elif mode == "Assigned Tasks":
            for ag_id in range(self.pcf.team_size):
                if ag_id not in self.pcf.agent_assigned_task:
                    continue
                current_task_id = None
                for assign_t, task_id in self.pcf.agent_assigned_task[ag_id]:
                    if assign_t <= self.pcf.cur_tstep:
                        current_task_id = task_id

                if current_task_id is None:
                    continue

                seq_task = self.pcf.seq_tasks[current_task_id]
                for i, task in enumerate(seq_task.tasks):
                    task_t = task.events["finished"]["timestep"]
                    if task.state in ["assigned", "newlyassigned"] and task_t >= self.pcf.cur_tstep:
                        self.set_task_visibility(current_task_id, i, True)

        self.show_task_index()


    def show_tasks_by_click(self, _) -> None:
        self.show_tasks()


    def show_single_task(self, task_id:int, seq_id:int=0, ignore:int=0) -> None:
        visible = False
        if ignore:
            visible = True
        else:
            mode = self.task_shown.get()
            if mode == "All Tasks":
                visible = True
            elif mode == "Assigned Tasks":
                task = self.pcf.seq_tasks[task_id].tasks[seq_id]
                visible = task.state in ["assigned", "newlyassigned"]
            elif mode == "Next Errand":
                task = self.pcf.seq_tasks[task_id].tasks[seq_id]
                if seq_id == 0:
                    visible = task.state in ["assigned", "newlyassigned"]
                else:
                    last_task = self.pcf.seq_tasks[task_id].tasks[seq_id-1]
                    last_t = last_task.events["finished"]["timestep"]
                    time_t = task.events["finished"]["timestep"]
                    visible = (
                        last_t <= self.pcf.cur_tstep and
                        time_t > self.pcf.cur_tstep and
                        task.state in ["assigned", "newlyassigned"]
                    )
            elif mode != "none":
                task = self.pcf.seq_tasks[task_id].tasks[seq_id]
                visible = (task.state == mode)

        self.set_task_visibility(task_id, seq_id, visible)


    def hide_single_task(self, task_id, seq_id) -> None:
        self.set_task_visibility(task_id, seq_id, False)


    def show_static_loc(self) -> None:
        """ Show the static locations (e.g., start locations)
        """
        _os_ = tk.DISABLED if self.show_static.get() is True else tk.HIDDEN
        _ts_ = tk.DISABLED if (self.show_ag_idx.get() is True and\
            self.show_static.get() is True) else tk.HIDDEN
        self.pcf.canvas.itemconfig(self.AGENT_START_OBJ_TAG, state=_os_)
        self.pcf.canvas.itemconfig(self.AGENT_START_TEXT_TAG, state=_ts_)


    def move_agents_per_timestep(self) -> None:
        """ Move agents forward from cur_tstep, adding cur_tstep by 1.
        """
        if self.pcf.cur_tstep+1 > min(self.pcf.makespan, self.pcf.end_tstep):
            return

        if self.pcf.window_size is not None:
            target_timestep = min(self.pcf.cur_tstep + self.pcf.window_size, self.pcf.end_tstep)
            target_idx = target_timestep - self.pcf.start_tstep
            if any(target_idx >= len(agent.path) for agent in self.pcf.agents.values()):
                self.pcf.ensure_paths_through(target_timestep)

        self.next_button.config(state=tk.DISABLED)
        _rad_ = ((1 - 2*DIR_OFFSET) - 0.1*2) * self.pcf.tile_size/2
        substeps = self.pcf.animation_substeps
        if substeps < 1:
            substeps = 1

        # Update the next timestep for each agent
        next_tstep = {}
        for (ag_id, agent) in self.pcf.agents.items():
            next_t = min(self.pcf.cur_tstep+1 - self.pcf.start_tstep, len(agent.path)-1)
            next_tstep[ag_id] = next_t

        for _m_ in range(substeps):
            if _m_ == substeps // 2:
                self.set_time_labels(self.pcf.cur_tstep+1)

            for (ag_id, agent) in self.pcf.agents.items():
                cur_angle = get_angle(agent.agent_obj.loc[2])
                direction = (agent.path[next_tstep[ag_id]][1] - agent.agent_obj.loc[1],
                             agent.path[next_tstep[ag_id]][0] - agent.agent_obj.loc[0])
                cur_move = (direction[0] * (self.pcf.tile_size / substeps),
                            direction[1] * (self.pcf.tile_size / substeps))
                cur_rotation = get_rotation(agent.agent_obj.loc[2],
                                            agent.path[next_tstep[ag_id]][2])
                next_ang = cur_rotation*(math.pi/2)/(substeps)

                # Move agent
                _cos = math.cos(cur_angle + next_ang * (_m_+1)) - math.cos(cur_angle+next_ang*_m_)
                _sin = -1 * (math.sin(cur_angle+ next_ang*(_m_+1))-math.sin(cur_angle+next_ang*_m_))
                self.pcf.canvas.move(agent.agent_obj.obj, cur_move[0], cur_move[1])
                self.pcf.canvas.move(agent.agent_obj.text, cur_move[0], cur_move[1])
                if self.pcf.agent_model == "MAPF_T":
                    self.pcf.canvas.move(agent.dir_obj, cur_move[0], cur_move[1])
                    self.pcf.canvas.move(agent.dir_obj, _rad_ * _cos, _rad_ * _sin)
                    
            
            self.clear_agent_selection(moving=True)
            for ag_idx in self.pcf.shown_path_agents:
                first_errand_t = self.show_colorful_errands(ag_idx, moving=True)
                if first_errand_t != -1:
                    self.show_ag_plan(ag_idx, first_errand_t, moving=True)
                    
            self.pcf.canvas.update()
            time.sleep(self.pcf.delay)

        # Update the location of each agent
        for (ag_id, agent) in self.pcf.agents.items():
            agent.agent_obj.loc = (agent.path[next_tstep[ag_id]][0],
                                   agent.path[next_tstep[ag_id]][1],
                                   agent.path[next_tstep[ag_id]][2])
        self.pcf.cur_tstep += 1
        self.next_button.config(state=tk.NORMAL)

        # Change tasks' states after cur_tstep += 1
        if not self.pcf.event_tracker:
            return
        
        self.update_event_list(self.event_listbox, 0)
        self.update_event_list(self.pop_event_listbox, 1)
        # If popup window location list exists, update it too
        if self.pop_location_listbox and self.pop_location_listbox.winfo_exists():
            # Extract grid location info from popup window title
            title = self.pop_gui_window.title()
            if "Location" in title:
                # Parse coordinates from title "Event List - Location (x, y)"
                match = re.search(r'Location \((\d+), (\d+)\)', title)
                if match:
                    grid_x, grid_y = int(match.group(1)), int(match.group(2))
                    self.update_location_event_list(self.pop_location_listbox)
        self.update_error_list(self.conflict_listbox)
        if self.pcf.cur_tstep == self.pcf.event_tracker["aTime"][self.pcf.event_tracker["aid"]]:
            # from unassigned to assigned
            for (global_task_id, ag_id) in self.pcf.events["assigned"][self.pcf.cur_tstep].items():
                task_id = global_task_id // self.pcf.max_seq_num
                seq_id = global_task_id % self.pcf.max_seq_num
                self.pcf.seq_tasks[task_id].tasks[seq_id].state = "assigned"
                self.change_task_color(task_id, seq_id, TASK_COLORS["assigned"])
                if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                    self.show_single_task(task_id, seq_id)
            self.pcf.event_tracker["aid"] += 1

        if self.pcf.cur_tstep == self.pcf.event_tracker["fTime"][self.pcf.event_tracker["fid"]]:
            # from assigned to finished
            for (global_task_id, ag_id) in self.pcf.events["finished"][self.pcf.cur_tstep].items():
                task_id = global_task_id // self.pcf.max_seq_num
                seq_id = global_task_id % self.pcf.max_seq_num
                self.pcf.seq_tasks[task_id].tasks[seq_id].state = "finished"
                self.change_task_color(task_id, seq_id, TASK_COLORS["finished"])
                if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                    self.show_single_task(task_id, seq_id)
                    tsk = self.pcf.seq_tasks[task_id].tasks
                    if len(tsk)-1 > seq_id:
                        self.show_single_task(task_id, seq_id+1)
            self.pcf.event_tracker["fid"] += 1
        self.update_agent_colors()
        self.raise_agent_canvas_items()
        

    def back_agents_per_timestep(self) -> None:
        """ Move agents one step backward in time, reducing cur_tstep by 1.
        """
        if self.pcf.cur_tstep == self.pcf.start_tstep:
            return

        self.prev_button.config(state=tk.DISABLED)
        prev_timestep = max(self.pcf.cur_tstep-1, 0)

        # Move the event tracker backward
        prev_aid = max(self.pcf.event_tracker["aid"]-1, 0)
        prev_fid = max(self.pcf.event_tracker["fid"]-1, 0)
        prev_agn_time = self.pcf.event_tracker["aTime"][prev_aid]
        prev_fin_time = self.pcf.event_tracker["fTime"][prev_fid]

        if self.pcf.cur_tstep == prev_fin_time:  # from finished to assigned
            for (global_task_id, ag_id) in self.pcf.events["finished"][prev_fin_time].items():
                task_id = global_task_id // self.pcf.max_seq_num
                seq_id  = global_task_id % self.pcf.max_seq_num
                assert self.pcf.seq_tasks[task_id].tasks[seq_id].state == "finished"
                self.pcf.seq_tasks[task_id].tasks[seq_id].state = "assigned"
                self.change_task_color(task_id, seq_id, TASK_COLORS["assigned"])
                if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                    self.show_single_task(task_id, seq_id)
            self.pcf.event_tracker["fid"] = prev_fid

        if self.pcf.cur_tstep == prev_agn_time:  # from assigned to unassigned
            for (global_task_id, ag_id) in self.pcf.events["assigned"][prev_agn_time].items():
                task_id = global_task_id // self.pcf.max_seq_num
                seq_id = global_task_id % self.pcf.max_seq_num
                assert self.pcf.seq_tasks[task_id].tasks[seq_id].state == "assigned"
                self.pcf.seq_tasks[task_id].tasks[seq_id].state = "unassigned"
                self.change_task_color(task_id, seq_id, TASK_COLORS["unassigned"])
                if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                    self.show_single_task(task_id, seq_id)
            self.pcf.event_tracker["aid"] = prev_aid
            prev_aid = max(self.pcf.event_tracker["aid"]-1, 0)
            prev_agn_time = self.pcf.event_tracker["aTime"][prev_aid]

        # Compute the previous location
        prev_loc:Dict[int, Tuple[int, int]] = {}
        relative_prev_t = prev_timestep - self.pcf.start_tstep
        for (ag_id, agent) in self.pcf.agents.items():
            if relative_prev_t > len(agent.path)-1:
                prev_loc[ag_id] = (agent.path[-1][0],
                                   agent.path[-1][1],
                                   agent.path[-1][2])
            else:
                prev_loc[ag_id] = (agent.path[relative_prev_t][0],
                                   agent.path[relative_prev_t][1],
                                   agent.path[relative_prev_t][2])

        # Move the agents backward
        _rad_ = ((1 - 2*DIR_OFFSET) - 0.1*2) * self.pcf.tile_size/2
        substeps = self.pcf.animation_substeps
        if substeps < 1:
            substeps = 1
        for _m_ in range(substeps):
            if _m_ == substeps // 2:
                self.set_time_labels(prev_timestep)
            for (ag_id, agent) in self.pcf.agents.items():
                cur_angle = get_angle(agent.agent_obj.loc[2])
                direction = (prev_loc[ag_id][1] - agent.agent_obj.loc[1],
                             prev_loc[ag_id][0] - agent.agent_obj.loc[0])
                cur_move = (direction[0] * (self.pcf.tile_size / substeps),
                            direction[1] * (self.pcf.tile_size / substeps))
                cur_rotation = get_rotation(agent.agent_obj.loc[2], prev_loc[ag_id][2])
                next_ang = cur_rotation*(math.pi/2)/(substeps)

                # Move agent
                _cos = math.cos(cur_angle+next_ang*(_m_+1)) - math.cos(cur_angle + next_ang*_m_)
                _sin = -1*(math.sin(cur_angle+next_ang*(_m_+1))-math.sin(cur_angle + next_ang*_m_))
                self.pcf.canvas.move(agent.agent_obj.obj, cur_move[0], cur_move[1])
                self.pcf.canvas.move(agent.agent_obj.text, cur_move[0], cur_move[1])
                if self.pcf.agent_model == "MAPF_T":
                    self.pcf.canvas.move(agent.dir_obj, cur_move[0], cur_move[1])
                    self.pcf.canvas.move(agent.dir_obj, _rad_*_cos, _rad_*_sin)
            self.pcf.canvas.update()
            time.sleep(self.pcf.delay)
        for (ag_id, agent) in self.pcf.agents.items():
            agent.agent_obj.loc = prev_loc[ag_id]

        self.pcf.cur_tstep = prev_timestep
        
        self.clear_agent_selection(moving=True)
        for ag_idx in self.pcf.shown_path_agents:
            first_errand_t = self.show_colorful_errands(ag_idx, moving=True)
            if first_errand_t != -1:
                self.show_ag_plan(ag_idx, first_errand_t, moving=True)
        
        self.update_event_list(self.event_listbox, 0)
        self.update_event_list(self.pop_event_listbox, 1)
        # If popup window location list exists, update it too
        if self.pop_location_listbox and self.pop_location_listbox.winfo_exists():
            # Extract grid location info from popup window title
            title = self.pop_gui_window.title()
            if "Location" in title:
                # Parse coordinates from title "Event List - Location (x, y)"
                match = re.search(r'Location \((\d+), (\d+)\)', title)
                if match:
                    grid_x, grid_y = int(match.group(1)), int(match.group(2))
                    self.update_location_event_list(self.pop_location_listbox)
        self.update_error_list(self.conflict_listbox)
        self.update_agent_colors()
        self.raise_agent_canvas_items()
        self.prev_button.config(state=tk.NORMAL)
        self.next_button.config(state=tk.NORMAL)


    def move_agents(self) -> None:
        """ Move agents constantly until pause or end_tstep is reached.
        """
        self.run_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)
        self.next_button.config(state=tk.DISABLED)
        self.prev_button.config(state=tk.DISABLED)
        self.update_button.config(state=tk.DISABLED)
        self.restart_button.config(state=tk.DISABLED)
        self.task_shown.config(state=tk.DISABLED)

        self.is_run.set(True)
        while self.pcf.cur_tstep < min(self.pcf.makespan, self.pcf.end_tstep):
            if self.is_run.get() is True:
                self.move_agents_per_timestep()
                if self.pcf.time_unit != "tick":
                    time.sleep(self.pcf.delay * 2)
                else:
                    time.sleep(self.pcf.delay)
            else:
                break

        self.run_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.NORMAL)
        self.next_button.config(state=tk.NORMAL)
        self.prev_button.config(state=tk.NORMAL)
        self.update_button.config(state=tk.NORMAL)
        self.restart_button.config(state=tk.NORMAL)
        self.task_shown.config(state=tk.NORMAL)


    def pause_agents(self) -> None:
        self.is_run.set(False)
        self.pause_button.config(state=tk.DISABLED)
        self.run_button.config(state=tk.NORMAL)
        self.next_button.config(state=tk.NORMAL)
        self.prev_button.config(state=tk.NORMAL)
        self.restart_button.config(state=tk.NORMAL)
        self.pcf.canvas.after(200, lambda: self.pause_button.config(state=tk.NORMAL))


    def update_curtime(self) -> None:
        """ Update the agents and tasks' colors to the cur_tstep
        """
        if self.new_time.get() > self.pcf.end_tstep:
            print("The target time is larger than the ending time")
            self.new_time.set(self.pcf.end_tstep)

        self.pcf.cur_tstep = self.new_time.get()
        self.set_time_labels(self.pcf.cur_tstep)
        if self.pcf.window_size is not None:
            target_timestep = min(self.pcf.cur_tstep + self.pcf.window_size, self.pcf.end_tstep)
            target_idx = target_timestep - self.pcf.start_tstep
            if any(target_idx >= len(agent.path) for agent in self.pcf.agents.values()):
                self.pcf.ensure_paths_through(target_timestep)
        
        # Change tasks' and agents' colors according to assigned timesteps
        for (task_id, seq_task) in self.pcf.seq_tasks.items():
            for (seq_id, task) in enumerate(seq_task.tasks):
                task.state = "unassigned"  # Initialize all the task states to unassigned

        for (task_id, seq_id) in self.pcf.rendered_tasks:
            self.change_task_color(task_id, seq_id, TASK_COLORS["unassigned"])
            self.hide_single_task(task_id, seq_id)

        for a_id, a_time in enumerate(self.pcf.event_tracker["aTime"]):
            if a_time == -1:
                self.pcf.event_tracker["aid"] = a_id
                break
            if a_time <= self.pcf.cur_tstep:
                for (global_task_id, ag_id) in self.pcf.events["assigned"][a_time].items():
                    task_id = global_task_id // self.pcf.max_seq_num
                    seq_id = global_task_id % self.pcf.max_seq_num
                    self.pcf.seq_tasks[task_id].tasks[seq_id].state = "assigned"
                    self.change_task_color(task_id, seq_id, TASK_COLORS["assigned"])
                    if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                        self.show_single_task(task_id, seq_id)
            else:  # a_time > self.pcf.cur_tstep
                self.pcf.event_tracker["aid"] = a_id
                break

        # Change tasks' colors according to finished timesteps
        for f_id, f_time in enumerate(self.pcf.event_tracker["fTime"]):
            if f_time == -1:
                break
            if f_time <= self.pcf.cur_tstep:
                for (global_task_id, ag_id) in self.pcf.events["finished"][f_time].items():
                    task_id = global_task_id // self.pcf.max_seq_num
                    seq_id = global_task_id % self.pcf.max_seq_num
                    self.pcf.seq_tasks[task_id].tasks[seq_id].state = "finished"
                    self.change_task_color(task_id, seq_id, TASK_COLORS["finished"])
                    if not self.pcf.shown_path_agents or ag_id in self.pcf.shown_path_agents:
                        self.show_single_task(task_id, seq_id)
            else:
                self.pcf.event_tracker["fid"] = f_id
                break

        for (ag_id, agent_) in self.pcf.agents.items():
            # Re-generate agent objects
            tstep = min(self.pcf.cur_tstep - self.pcf.start_tstep, len(agent_.path)-1)
            self.pcf.canvas.delete(agent_.agent_obj.obj)
            self.pcf.canvas.delete(agent_.agent_obj.text)
            agent_.agent_obj = self.pcf.render_obj(ag_id, agent_.path[tstep], "oval",
                                                   AGENT_COLORS[AgentStatus.NORMAL.color_key],
                                                   tk.NORMAL, 0.05, str(ag_id))
            
            if self.pcf.agent_model == "MAPF_T":
                self.pcf.canvas.delete(agent_.dir_obj)
                dir_loc = get_dir_loc(agent_.path[tstep])
                agent_.dir_obj = self.pcf.canvas.create_oval(dir_loc[0] * self.pcf.tile_size,
                                                             dir_loc[1] * self.pcf.tile_size,
                                                             dir_loc[2] * self.pcf.tile_size,
                                                             dir_loc[3] * self.pcf.tile_size,
                                                             fill="navy",
                                                             tag="dir",
                                                             state=tk.DISABLED,
                                                             outline="")
            self._tag_agent_dynamic_canvas_items(agent_)
        self.show_tasks()
        self.show_agent_index()
        
        
        self.update_event_list(self.event_listbox, 0)
        self.update_event_list(self.pop_event_listbox, 1)
        # If popup window location list exists, update it too
        if self.pop_location_listbox and self.pop_location_listbox.winfo_exists():
            # Extract grid location info from popup window title
            title = self.pop_gui_window.title()
            if "Location" in title:
                # Parse coordinates from title "Event List - Location (x, y)"
                match = re.search(r'Location \((\d+), (\d+)\)', title)
                if match:
                    grid_x, grid_y = int(match.group(1)), int(match.group(2))
                    self.update_location_event_list(self.pop_location_listbox)
        self.update_error_list(self.conflict_listbox)
        self.update_agent_colors()
        self.pcf.canvas.update()
