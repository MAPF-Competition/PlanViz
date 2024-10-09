# -*- coding: UTF-8 -*-
""" Plan Visualizer with rotation agents
This is a script for visualizing the plan for the League of Robot Runners.
All rights reserved.
"""

import math
from typing import List, Tuple, Dict, Set
import tkinter as tk
from tkinter import ttk
import time
from util import TASK_COLORS, AGENT_COLORS, DIR_OFFSET, TEXT_SIZE, \
    get_angle, get_dir_loc, get_rotation
from plan_config import PlanConfig


class PlanViz:
    """ This is the control panel of PlanViz
    """
    def __init__(self, plan_config, _grid, _ag_idx, _task_idx, _static, _conf_ag):
        print("===== Initialize PlanViz    =====")

        # Load the yaml file or the input arguments
        self.pcf:PlanConfig = plan_config
        self.pcf.canvas.bind("<Button-3>", self.show_ag_plan_by_click)

        # This is what enables using the mouse:
        self.pcf.canvas.bind("<ButtonPress-1>", self.__move_from)
        self.pcf.canvas.bind("<B1-Motion>", self.__move_to)
        # linux scroll
        self.pcf.canvas.bind("<Button-4>", self.__wheel)
        self.pcf.canvas.bind("<Button-5>", self.__wheel)
        # windows scroll
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
        # Respond to Linux (event.num) or Windows (event.delta) wheel event
        if event.num == 5 or event.delta == -120:  # scroll down, smaller
            threshold = round(min(self.pcf.width, self.pcf.height) * self.pcf.tile_size)
            if threshold < 30:
                return  # image is less than 30 pixels
            scale /= 1.10
            self.pcf.tile_size /= 1.10
        if event.num == 4 or event.delta == 120:  # scroll up, bigger
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
