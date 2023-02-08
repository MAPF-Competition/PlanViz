# -*- coding: UTF-8 -*-
""" Plan Visualizer
This is a script for visualizing the plan for MAPF.
"""

import os
import sys
import logging
import argparse
from typing import List, Tuple, Dict
from tkinter import *
import time
import yaml
import numpy as np


COLORS: List[str] = ["purple", "pink", "yellow", "blue", "violet", "tomato", "green",
                     "cyan", "brown", "olive", "gray", "crimson"]


MAP_CONFIG: Dict[str,Dict] = {
    "maze-32-32-2": {"pixel_per_move": 5, "moves": 5, "delay": 0.08},
    "random-32-32-20": {"pixel_per_move": 5, "moves": 5, "delay": 0.08},
    "room-32-32-4": {"pixel_per_move": 5, "moves": 5, "delay": 0.08},
    "warehouse-10-20-10-2-1": {"pixel_per_move": 3, "moves": 3, "delay": 0.08}
}


def get_map_name(in_file:str) -> str:
    """Get the map name from the file name

    Args:
        in_file (str): the path of the map file

    Returns:
        str: the name of the map
    """
    return in_file.split("/")[-1].split(".")[0]

class BaseObj:
    def __init__(self, _obj_, _text_, _loc_, _color_) -> None:
        self.obj = _obj_
        self.text = _text_
        self.loc = _loc_
        self.color = _color_

class Agent:
    def __init__(self, _idx_, _ag_obj_:BaseObj,
                 _start_:BaseObj, _goal_:BaseObj, _path_:List) -> None:
        self.idx = _idx_
        self.agent_obj = _ag_obj_
        self.start_obj = _start_
        self.goal_obj = _goal_
        self.path = _path_

class PlanVis:
    """Render MAPF instance
    """
    def __init__(self, in_arg) -> None:
        print("===== Initialize MAPF visualizer =====")

        # Load the yaml file or the input arguments
        tmp_config: Dict = dict()

        if in_arg.config is not None:
            config_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), in_arg.config)
            with open(config_dir, 'r') as fin:
                tmp_config = yaml.load(fin, Loader=yaml.FullLoader)
        else:
            tmp_config["map_file"] = in_arg.map
            tmp_config["scen_file"] = in_arg.scen
            tmp_config["path_file"] = in_arg.path
            tmp_config["num_of_agents"] = in_arg.num_of_agents
            tmp_config["show_grid"] = in_arg.show_grid
            tmp_config["show_ag_idx"] = in_arg.show_ag_idx
            tmp_config["show_static"] = in_arg.show_static
            tmp_config["show_conf_ag"] = in_arg.show_conf_ag

            if in_arg.pixel_per_move is not None:
                tmp_config["pixel_per_move"] = in_arg.pixel_per_move
            if in_arg.moves is not None:
                tmp_config["moves"] = in_arg.moves
            if in_arg.delay is not None:
                tmp_config["delay"] = in_arg.delay

        if "pixel_per_move" not in tmp_config.keys():
            map_name = get_map_name(tmp_config["map_file"])
            assert map_name in MAP_CONFIG.keys()
            tmp_config["pixel_per_move"] = MAP_CONFIG[map_name]["pixel_per_move"]

        if "moves" not in tmp_config.keys():
            map_name = get_map_name(tmp_config["map_file"])
            assert map_name in MAP_CONFIG.keys()
            tmp_config["moves"] = MAP_CONFIG[map_name]["moves"]

        if "delay" not in tmp_config.keys():
            map_name = get_map_name(tmp_config["map_file"])
            assert map_name in MAP_CONFIG.keys()
            tmp_config["delay"] = MAP_CONFIG[map_name]["delay"]

        assert "map_file" in tmp_config.keys()
        assert "scen_file" in tmp_config.keys()
        assert "path_file" in tmp_config.keys()
        assert "num_of_agents" in tmp_config.keys()
        assert "delay" in tmp_config.keys()
        assert "pixel_per_move" in tmp_config.keys()
        assert "moves" in tmp_config.keys()

        # Assign configuration to the variable
        self.map_file:str = tmp_config["map_file"]
        self.scen_file:str = tmp_config["scen_file"]
        self.path_file:str = tmp_config["path_file"]
        self.num_of_agents:int = tmp_config["num_of_agents"]

        self.moves:int = tmp_config["moves"]
        self.ppm:int = tmp_config["pixel_per_move"]
        self.tile_size:int = self.ppm * self.moves
        self.text_size:int = self.tile_size//2
        self.delay:int = tmp_config["delay"]

        self.width:int = -1
        self.height:int = -1
        self.env_map:List[List[bool]] = list()
        self.grids:List = list()

        self.agents:Dict = dict()
        self.makespan:int = -1

        self.load_map()
        (start_loc, goal_loc) = self.load_init_loc()
        paths = self.load_paths()
        self.conflicts:Dict = self.load_conflicts(self.path_file)
        self.conflict_agents:set = self.get_conflict_agents(self.conflicts)

        self.window = Tk()

        self.cur_timestep = 0

        self.is_run = BooleanVar(self.window)
        self.is_run.set(False)

        self.is_grid = BooleanVar()
        self.is_grid.set(tmp_config["show_grid"])

        self.show_ag_idx = BooleanVar()
        self.show_ag_idx.set(tmp_config["show_ag_idx"])

        self.show_static = BooleanVar()
        self.show_static.set(tmp_config["show_static"])

        self.show_all_conf_ag = BooleanVar()
        self.show_all_conf_ag.set(tmp_config["show_conf_ag"])

        # Show MAPF instance
        self.canvas = Canvas(width=(self.width+1) * self.tile_size,
                             height=(self.height+1) * self.tile_size,
                             bg="white")
        self.canvas.grid(row=1, column=0)
        self.canvas.configure(scrollregion = self.canvas.bbox("all"))

        # This is what enables using the mouse:
        self.canvas.bind("<ButtonPress-1>", self.__move_from)
        self.canvas.bind("<B1-Motion>", self.__move_to)
        #linux scroll
        self.canvas.bind("<Button-4>", self.__wheel)
        self.canvas.bind("<Button-5>", self.__wheel)
        #windows scroll
        self.canvas.bind("<MouseWheel>",self.__wheel)

        self.render_env()
        self.render_agents(start_loc=start_loc, goal_loc=goal_loc, paths=paths)

        # Generate the GUI pannel
        print("Rendering the pannel... ", end="")
        self.frame = Frame(self.window)
        self.frame.grid(row=1, column=1,sticky="n")
        row_idx = 0

        self.timestep_label = Label(self.frame,
                              text = f"Timestep: {self.cur_timestep:03d}",
                              font=("Arial", self.text_size + 10))
        self.timestep_label.grid(row=row_idx, column=0, columnspan=10, sticky="wn")
        row_idx += 1

        self.run_button = Button(self.frame, text="Play", font=("Ariel",self.text_size),
                                 command=self.move_agents)
        self.run_button.grid(row=row_idx, column=0, sticky="wn")
        self.pause_button = Button(self.frame, text="Pause", font=("Ariel",self.text_size),
                                   command=self.pause_agents)
        self.pause_button.grid(row=row_idx, column=1, sticky="wn")
        self.resume_zoom_button = Button(self.frame, text="Fullsize", font=("Ariel",self.text_size),
                                         command=self.resumeZoom)
        self.resume_zoom_button.grid(row=row_idx, column=2, columnspan=2, sticky="w")
        row_idx += 1

        self.next_button = Button(self.frame, text="Next", font=("Ariel",self.text_size),
                                  command=self.move_agents_per_timestep)
        self.next_button.grid(row=row_idx, column=0, sticky="w")
        self.prev_button = Button(self.frame, text="Prev", font=("Ariel",self.text_size),
                                  command=self.back_agents_per_timestep)
        self.prev_button.grid(row=row_idx, column=1, sticky="w")
        self.restart_button = Button(self.frame, text="Reset", font=("Ariel",self.text_size),
                                     command=self.restart_timestep)
        self.restart_button.grid(row=row_idx, column=2, columnspan=2, sticky="wn")
        row_idx += 1

        self.grid_button = Checkbutton(self.frame, text="Show grids", font=("Ariel",self.text_size),
                                       variable=self.is_grid, onvalue=True, offvalue=False,
                                       command=self.show_grid)
        self.grid_button.grid(row=row_idx, column=0, columnspan=4, sticky="w")
        row_idx += 1

        self.id_button = Checkbutton(self.frame, text="Show indices", font=("Ariel",self.text_size),
                                     variable=self.show_ag_idx, onvalue=True, offvalue=False,
                                     command=self.show_index)
        self.id_button.grid(row=row_idx, column=0, columnspan=4, sticky="w")
        row_idx += 1

        self.static_button = Checkbutton(self.frame, text="Show start/goal locations",
                                         font=("Ariel",self.text_size),
                                         variable=self.show_static, onvalue=True, offvalue=False,
                                         command=self.show_static_loc)
        self.static_button.grid(row=row_idx, column=0, columnspan=4, sticky="w")
        row_idx += 1

        self.show_all_conf_ag_button = Checkbutton(self.frame, text="Show colliding agnets",
                                                   font=("Ariel",self.text_size),
                                                   variable=self.show_all_conf_ag,
                                                   onvalue=True, offvalue=False,
                                                   command=self.mark_conf_agents)
        self.show_all_conf_ag_button.grid(row=row_idx, column=0, columnspan=4, sticky="w")
        row_idx += 1

        tmp_label = Label(self.frame, text="Start timestep: ", font=("Ariel",self.text_size))
        tmp_label.grid(row=row_idx, column=0, columnspan=2, sticky="w")
        self.new_time = IntVar()
        self.start_time_entry = Entry(self.frame, width=5, textvariable=self.new_time,
                                      validatecommand=self.update_curtime)
        self.start_time_entry.grid(row=row_idx, column=2, sticky="w")
        self.update_button = Button(self.frame, text="Go", font=("Ariel",self.text_size),
                                    command=self.update_curtime)
        self.update_button.grid(row=row_idx, column=3, sticky="w")
        row_idx += 1

        tmp_label2 = Label(self.frame, text="List of collisions", font=("Ariel",self.text_size),)
        tmp_label2.grid(row=row_idx, column=0, columnspan=3, sticky="w")
        row_idx += 1

        self.shown_conflicts:Dict[str, List[List,bool]] = dict()
        self.conflict_listbox = Listbox(self.frame,
                                        width=28,
                                        font=("Ariel",self.text_size),
                                        selectmode=EXTENDED)
        conf_id = 0
        for _timestep_ in sorted(self.conflicts.keys(), reverse=True):
            for _conf_ in self.conflicts[_timestep_]:
                conf_str = str()
                conf_str = "a" + str(_conf_[0]) + ", a" + str(_conf_[1])
                if _conf_[-1] == "V":
                    conf_str += ", v=" + str(_conf_[2])
                elif _conf_[-1] == "E":
                    conf_str += ", e=(" + str(_conf_[2]) + "," + str(_conf_[3]) + ")"
                conf_str += ", t=" + str(_conf_[4])

                self.conflict_listbox.insert(conf_id, conf_str)
                self.shown_conflicts[conf_str] = [_conf_, False]
        self.conflict_listbox.grid(row=row_idx, column=0, columnspan=5, sticky="w")
        self.conflict_listbox.bind('<<ListboxSelect>>', self.select_conflict)
        self.conflict_listbox.bind('<Double-1>', self.move_to_conflict)

        scrollbar = Scrollbar(self.frame, orient="vertical")
        self.conflict_listbox.config(yscrollcommand = scrollbar.set)
        scrollbar.config(command=self.conflict_listbox.yview)
        scrollbar.grid(row=row_idx, column=4, sticky="w")
        row_idx += 1

        print("Done!")

        # Adjust window size
        self.frame.update()
        wd_width = str((self.width+1) * self.tile_size + 300)
        wd_height = str(max((self.height+1) * self.tile_size, self.frame.winfo_height() + 10))
        self.window.geometry(wd_width + "x" + wd_height)
        self.window.title("MAPF Instance")
        print("=====            DONE            =====")


    def change_ag_color(self, ag_idx:int, color:str) -> None:
        self.canvas.itemconfig(self.agents[ag_idx].agent_obj.obj, fill=color)
        self.agents[ag_idx].agent_obj.color = color
        if self.show_ag_idx.get() is True:
            self.canvas.itemconfig(self.agents[ag_idx].agent_obj.text, fill="black")
        else:
            self.canvas.itemconfig(self.agents[ag_idx].agent_obj.text, fill=color)


    def select_conflict(self, event):
        selected_indices = event.widget.curselection()  # get all selected indices

        for _conf_ in self.shown_conflicts.values():
            self.change_ag_color(_conf_[0][0], "deepskyblue")
            self.change_ag_color(_conf_[0][1], "deepskyblue")
            _conf_[1] = False
        for _sid_ in selected_indices:
            _conf_ = self.shown_conflicts[self.conflict_listbox.get(_sid_)]
            self.change_ag_color(_conf_[0][0], "red")
            self.change_ag_color(_conf_[0][1], "red")
            self.shown_conflicts[self.conflict_listbox.get(_sid_)][1] = True


    def restart_timestep(self):
        self.new_time.set(0)
        self.update_curtime()


    def move_to_conflict(self, event):
        if self.is_run.get() is True:
            return

        for _conf_ in self.shown_conflicts.values():
            self.change_ag_color(_conf_[0][0], "deepskyblue")
            self.change_ag_color(_conf_[0][1], "deepskyblue")
            _conf_[1] = False
        _sid_ = event.widget.curselection()[0]  # get all selected indices
        _conf_ = self.shown_conflicts[self.conflict_listbox.get(_sid_)]
        self.change_ag_color(_conf_[0][0], "red")
        self.change_ag_color(_conf_[0][1], "red")
        self.shown_conflicts[self.conflict_listbox.get(_sid_)][1] = True
        self.new_time.set(int(_conf_[0][4])-1)
        self.update_curtime()


    def __move_from(self, event):
        """ Remember previous coordinates for scrolling with the mouse """
        self.canvas.scan_mark(event.x, event.y)

    def __move_to(self, event):
        """ Drag (move) canvas to the new position """
        self.canvas.scan_dragto(event.x, event.y, gain=1)


    def __wheel(self, event):
        """ Zoom with mouse wheel """
        # x = self.canvas.canvasx(event.x)  # get coordinates of the event on the canvas
        # y = self.canvas.canvasy(event.y)
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
            self.canvas.itemconfigure(child_widget, font=("Ariel", int(self.text_size*scale)))
        self.canvas.configure(scrollregion = self.canvas.bbox("all"))

    def resumeZoom(self):
        __scale = self.ppm * self.moves / self.tile_size
        self.canvas.scale("all", 0, 0, __scale, __scale)
        self.tile_size = self.ppm * self.moves
        for child_widget in self.canvas.find_withtag("text"):
            self.canvas.itemconfigure(child_widget, font=("Ariel", self.text_size))
        self.canvas.configure(scrollregion = self.canvas.bbox("all"))
        self.canvas.update()

    def render_obj(self, _idx_, loc:Tuple[int], shape:str="rectangle", color:str="blue")->None:
        """Mark certain positions on the visualizer

        Args:
            loc (List, required): A list of locations on the map.
            shape (str, optional): The shape of marked on each location. Defaults to "rectangle".
            color (str, optional): The color of the mark. Defaults to "blue".
        """
        offset = 0.002 * self.tile_size
        tmp_canvas = None
        if shape == "rectangle":
            tmp_canvas = self.canvas.create_rectangle((loc[0]+offset) * self.tile_size,
                                                      (loc[1]+offset) * self.tile_size,
                                                      (loc[0]+1-offset) * self.tile_size,
                                                      (loc[1]+1-offset) * self.tile_size,
                                                      fill=color,
                                                      state="disable",
                                                      outline="")
        elif shape == "oval":
            tmp_canvas = self.canvas.create_oval((loc[0]+offset) * self.tile_size,
                                                 (loc[1]+offset) * self.tile_size,
                                                 (loc[0]+1-offset) * self.tile_size,
                                                 (loc[1]+1-offset) * self.tile_size,
                                                 fill=color,
                                                 state="disable",
                                                 outline="")
        else:
            logging.error("Undefined shape.")
            sys.exit()

        tmp_text = None
        if self.show_ag_idx.get() is True:
            tmp_text = self.canvas.create_text((loc[0]+0.5)*self.tile_size,
                                                (loc[1]+0.5)*self.tile_size,
                                                text=str(_idx_),
                                                fill="black",
                                                tag="text",
                                                state="disable",
                                                font=("Arial", self.text_size))
        else:
            tmp_text = self.canvas.create_text((loc[0]+0.51)*self.tile_size,
                                                (loc[1]+0.51)*self.tile_size,
                                                text=str(_idx_),
                                                fill=color,
                                                tag="text",
                                                state="disable",
                                                font=("Arial", self.text_size))
        return BaseObj(tmp_canvas, tmp_text, loc, color)


    def render_env(self) -> None:
        print("Rendering the environment ... ", end="")
        # Render grids
        _line_color_ = "grey" if self.is_grid.get() is True else "white"
        for rid in range(self.height):  # Render horizontal lines
            _line_ = self.canvas.create_line(rid * self.tile_size, 0,
                                             rid * self.tile_size, self.width * self.tile_size,
                                             tags="grid",
                                             fill=_line_color_)
            self.grids.append(_line_)
        for cid in range(self.width):  # Render vertical lines
            _line_ = self.canvas.create_line(0, cid * self.tile_size,
                                             self.height * self.tile_size, cid * self.tile_size,
                                             tags="grid",
                                             fill=_line_color_)
            self.grids.append(_line_)

        # Render obstacles
        for rid, _cur_row_ in enumerate(self.env_map):
            for cid, _cur_ele_ in enumerate(_cur_row_):
                if _cur_ele_ is False:
                    self.canvas.create_rectangle(cid * self.tile_size,
                                                 rid * self.tile_size,
                                                 (cid+1)*self.tile_size,
                                                 (rid+1)*self.tile_size,
                                                 fill="black")
        # Render coordinates
        for cid in range(self.width):
            self.canvas.create_text((cid+0.5)*self.tile_size,
                                    (self.height+0.5)*self.tile_size,
                                    text=str(cid),
                                    fill="black",
                                    tag="coor",
                                    font=("Arial", int(self.tile_size*0.4)))
        for rid in range(self.height):
            self.canvas.create_text((self.width+0.5)*self.tile_size,
                                    (rid+0.5)*self.tile_size,
                                    text=str(rid),
                                    fill="black",
                                    tag="coor",
                                    font=("Arial", int(self.tile_size*0.4)))
        self.canvas.create_line(self.width * self.tile_size, 0,
                                self.width * self.tile_size, self.height * self.tile_size,
                                fill="black")
        self.canvas.create_line(0, self.height * self.tile_size,
                                self.width * self.tile_size, self.height * self.tile_size,
                                fill="black")
        print("Done!")


    def render_agents(self, start_loc:List, goal_loc:List, paths:List) -> None:
        print("Rendering the agents... ", end="")
        # Separate the render of static locations and agents so that agents can overlap
        tmp_starts = list()
        tmp_goals = list()
        for _ag_ in range(self.num_of_agents):
            start = self.render_obj(_ag_, start_loc[_ag_], "oval", "yellowgreen")
            goal = self.render_obj(_ag_, goal_loc[_ag_], "rectangle", "orange")
            tmp_starts.append(start)
            tmp_goals.append(goal)

        for _ag_ in range(self.num_of_agents):
            agent_obj = self.render_obj(_ag_, start_loc[_ag_], "oval", "deepskyblue")
            agent = Agent(_ag_, agent_obj, tmp_starts[_ag_], tmp_goals[_ag_], paths[_ag_])
            self.agents[_ag_] = agent
        self.show_static_loc()
        print("Done!")


    def mark_conf_agents(self) -> None:
        self.conflict_listbox.select_clear(0, self.conflict_listbox.size())
        _color_ = "red" if self.show_all_conf_ag.get() else "deepskyblue"
        for _conf_ in self.shown_conflicts.values():
            self.change_ag_color(_conf_[0][0], _color_)
            self.change_ag_color(_conf_[0][1], _color_)
            _conf_[1] = False


    def show_grid(self) -> None:
        if self.is_grid.get() is True:
            for _line_ in self.grids:
                self.canvas.itemconfig(_line_, fill="grey")
        else:
            for _line_ in self.grids:
                self.canvas.itemconfig(_line_, fill="white")


    def show_index(self) -> None:
        if self.show_static.get() is True and self.show_ag_idx.get() is True:
            for (_, _agent_) in self.agents.items():
                self.canvas.itemconfig(_agent_.agent_obj.text, fill="black")
                self.canvas.itemconfig(_agent_.start_obj.text, fill="black")
                self.canvas.itemconfig(_agent_.goal_obj.text, fill="black")

        elif self.show_static.get() is True and self.show_ag_idx.get() is False:
            for (_, _agent_) in self.agents.items():
                self.canvas.itemconfig(_agent_.agent_obj.text, fill=_agent_.agent_obj.color)
                self.canvas.itemconfig(_agent_.start_obj.text, fill=_agent_.start_obj.color)
                self.canvas.itemconfig(_agent_.goal_obj.text, fill=_agent_.goal_obj.color)

        elif self.show_static.get() is False and self.show_ag_idx.get() is True:
            for (_, _agent_) in self.agents.items():
                self.canvas.itemconfig(_agent_.agent_obj.text, fill="black")
                self.canvas.itemconfig(_agent_.start_obj.text, fill="white")
                self.canvas.itemconfig(_agent_.goal_obj.text, fill="white")

        else:
            for (_, _agent_) in self.agents.items():
                self.canvas.itemconfig(_agent_.agent_obj.text, fill=_agent_.agent_obj.color)
                self.canvas.itemconfig(_agent_.start_obj.text, fill="white")
                self.canvas.itemconfig(_agent_.goal_obj.text, fill="white")


    def show_static_loc(self) -> None:
        if self.show_static.get() is True:
            for (_, _agent_) in self.agents.items():
                self.canvas.itemconfig(_agent_.start_obj.obj, fill=_agent_.start_obj.color)
                self.canvas.itemconfig(_agent_.goal_obj.obj, fill=_agent_.goal_obj.color)
                if self.show_ag_idx.get() is True:
                    self.canvas.itemconfig(_agent_.start_obj.text, fill="black")
                    self.canvas.itemconfig(_agent_.goal_obj.text, fill="black")
                else:
                    self.canvas.itemconfig(_agent_.start_obj.text, fill=_agent_.start_obj.color)
                    self.canvas.itemconfig(_agent_.goal_obj.text, fill=_agent_.goal_obj.color)

        else:
            for (_, _agent_) in self.agents.items():
                self.canvas.itemconfig(_agent_.start_obj.obj, fill="white")
                self.canvas.itemconfig(_agent_.goal_obj.obj, fill="white")
                self.canvas.itemconfig(_agent_.start_obj.text, fill="white")
                self.canvas.itemconfig(_agent_.goal_obj.text, fill="white")


    def load_map(self, map_file:str = None) -> None:
        if map_file is None:
            map_file = self.map_file
        print("Loading map from " + map_file, end = '... ')

        with open(map_file, "r") as fin:
            fin.readline()  # ignore type
            self.height = int(fin.readline().strip().split(' ')[1])
            self.width  = int(fin.readline().strip().split(' ')[1])
            fin.readline()  # ingmore 'map' line
            for line in fin.readlines():
                out_line: List[bool] = list()
                for word in list(line.strip()):
                    if word == '.':
                        out_line.append(True)
                    else:
                        out_line.append(False)
                assert len(out_line) == self.width
                self.env_map.append(out_line)
        assert len(self.env_map) == self.height
        print("Done!")

    def load_init_loc(self, scen_file:str = None) -> Tuple[Dict]:
        if scen_file is None:
            scen_file = self.scen_file

        print("Loading scen from "+str(scen_file), end="... ")
        if not os.path.exists(scen_file):
            logging.warning("\nNo scen file is found!")
            return

        start_loc = dict()
        goal_loc = dict()
        with open(scen_file, "r") as fin:
            fin.readline()  # ignore the first line 'version 1'
            ag_counter:int = 0
            for line in fin.readlines():
                line_seg = line.split('\t')
                start_loc[ag_counter] = (int(line_seg[4]), int(line_seg[5]))
                goal_loc[ag_counter] = (int(line_seg[6]), int(line_seg[7]))

                ag_counter += 1
                if ag_counter == self.num_of_agents:
                    break

        print("Done!")
        return (start_loc, goal_loc)


    def load_paths(self, path_file:str = None):
        if path_file is None:
            path_file = self.path_file

        print("Loading paths from "+str(path_file), end="... ")
        if not os.path.exists(path_file):
            logging.warning("\nNo path file is found!")
            return

        paths = dict()
        with open(path_file, "r") as fin:
            ag_counter = 0
            for line in fin.readlines():
                if line.split(" ")[0] != "Agent":
                    break
                ag_idx = int(line.split(" ")[1].split(":")[0])
                paths[ag_idx] = list()
                for cur_loc in line.split(" ")[-1].split("->"):
                    if cur_loc == "\n":
                        continue
                    cur_x = int(cur_loc.split(",")[1].split(")")[0])
                    cur_y = int(cur_loc.split(",")[0].split("(")[1])
                    paths[ag_idx].append((cur_x, cur_y))
                ag_counter += 1

            self.num_of_agents = ag_counter

        for ag_idx in range(self.num_of_agents):
            if self.makespan < max(len(paths[ag_idx])-1, 0):
                self.makespan = max(len(paths[ag_idx])-1, 0)

        print("Done!")
        return paths


    @staticmethod
    def load_conflicts(in_file:str):
        if not os.path.exists(in_file):
            logging.warning("No conflict file is found!")
            return
        conflicts = dict()
        last_line = str()
        with open(in_file, "r") as fin:
            last_line = fin.readlines()[-1]
        with open(in_file, "r") as fin:
            while True:
                line = fin.readline()
                if line.rstrip('\n') == "Conflicts":
                    line = fin.readline()
                    while True:
                        line = fin.readline().rstrip('\n')
                        if line.rstrip('\n') == "---":
                            break
                        conf = line.split(",")
                        for i in range(5):
                            conf[i] = int(conf[i])
                        timestep = conf[4]
                        if timestep not in conflicts.keys():
                            conflicts[timestep] = list()
                        conflicts[timestep].append(conf)
                    break
                if line == last_line:
                    break
        return conflicts

    @staticmethod
    def get_conflict_agents(conflicts:Dict):
        conf_ags = set()
        for (_, conf_list) in conflicts.items():
            for conf in conf_list:
                conf_ags.add(conf[0])
                conf_ags.add(conf[1])
        return conf_ags


    def move_agents_per_timestep(self) -> None:
        self.next_button.config(state="disable")

        for _m_ in range(self.moves):
            if _m_ == self.moves // 2:
                self.timestep_label.config(text = f"Timestep: {self.cur_timestep+1:03d}")
            for (_, agent) in self.agents.items():
                next_timestep = min(self.cur_timestep+1, len(agent.path)-1)
                direction = (agent.path[next_timestep][0] - agent.agent_obj.loc[0],
                             agent.path[next_timestep][1] - agent.agent_obj.loc[1])
                cur_move = (direction[0] * (self.tile_size / self.moves),
                            direction[1] * (self.tile_size / self.moves))
                self.canvas.move(agent.agent_obj.obj, cur_move[0], cur_move[1])
                self.canvas.move(agent.agent_obj.text, cur_move[0], cur_move[1])

            self.canvas.update()
            time.sleep(self.delay)

        for (_, agent) in self.agents.items():
            next_timestep = min(self.cur_timestep+1, len(agent.path)-1)
            agent.agent_obj.loc = (agent.path[next_timestep][0],
                                   agent.path[next_timestep][1])
        self.cur_timestep += 1
        self.next_button.config(state="normal")


    def back_agents_per_timestep(self) -> None:
        if self.cur_timestep == 0:
            return

        self.prev_button.config(state="disable")

        prev_timestep = max(self.cur_timestep-1, 0)
        prev_loc:Dict[int, Tuple[int, int]] = dict()
        for (ag_idx, agent) in self.agents.items():
            if prev_timestep > len(agent.path)-1:
                prev_loc[ag_idx] = (agent.path[-1][0], agent.path[-1][1])
            else:
                prev_loc[ag_idx] = (agent.path[prev_timestep][0],
                                    agent.path[prev_timestep][1])

        for _m_ in range(self.moves):
            if _m_ == self.moves // 2:
                self.timestep_label.config(text = f"Timestep: {prev_timestep:03d}")
            for (ag_idx, agent) in self.agents.items():
                direction = (prev_loc[ag_idx][0] - agent.agent_obj.loc[0],
                             prev_loc[ag_idx][1] - agent.agent_obj.loc[1])
                cur_move = (direction[0] * (self.tile_size / self.moves),
                            direction[1] * (self.tile_size / self.moves))
                self.canvas.move(agent.agent_obj.obj, cur_move[0], cur_move[1])
                self.canvas.move(agent.agent_obj.text, cur_move[0], cur_move[1])

            self.canvas.update()
            time.sleep(self.delay)

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
        for (_idx_, _agent_) in self.agents.items():
            _color_ = _agent_.agent_obj.color
            self.canvas.delete(_agent_.agent_obj.obj)
            self.canvas.delete(_agent_.agent_obj.text)
            _time_ = min(self.cur_timestep, len(_agent_.path)-1)
            _agent_.agent_obj = self.render_obj(_idx_, _agent_.path[_time_], "oval", _color_)
            self.canvas.update()
        return


def main() -> None:
    """The main function of the visualizer.
    """
    parser = argparse.ArgumentParser(description='Plan visualizer for a MAPF instance')
    parser.add_argument('--config', type=str, help="use a yaml file as input")
    parser.add_argument('--map', type=str, help="Path to the map file")
    parser.add_argument('--scen', type=str, help="Path to the scen file")
    parser.add_argument('--path', type=str, help="Path to the path file")
    parser.add_argument('--n', type=int, default=np.inf, dest="num_of_agents",
                        help="Number of agents")
    parser.add_argument('--ppm', type=int, dest="pixel_per_move", help="Number of pixels per move")
    parser.add_argument('--mv', type=int, dest="moves", help="Number of moves per action")
    parser.add_argument('--delay', type=float, help="Wait time between timesteps")
    parser.add_argument('--grid', type=bool, default=False, dest="show_grid",
                        help="Show grid on the environment or not")
    parser.add_argument('--aid', type=bool, default=False, dest="show_ag_idx",
                        help="Show agent indices or not")
    parser.add_argument('--static', type=bool, default=False, dest="show_static",
                        help="Show start/goal locations or not")
    parser.add_argument('--ca', type=bool, default=False, dest="show_conf_ag",
                        help="Show all colliding agents")
    args = parser.parse_args()

    PlanVis(args)
    mainloop()


if __name__ == "__main__":
    main()
