# -*- coding: UTF-8 -*-
""" Plan Visualizer
This is a script for visualizing the plan for MAPF.
"""

import os
import sys
import logging
import argparse
from typing import List, Tuple, Dict
from tkinter import Tk, Canvas, Label, mainloop
import time
import yaml
import numpy as np

COLORS: List[str] = ["deepskyblue", "orange", "yellowgreen", "purple", "pink",
                     "yellow", "blue", "violet", "tomato", "green",
                     "cyan", "brown", "olive", "gray", "crimson"]


MAP_CONFIG: Dict[str,Dict] = {
    "maze-32-32-2": {"pixel_per_move": 5, "moves": 5, "delay": 0.08},
    "random-32-32-20": {"pixel_per_move": 5, "moves": 5, "delay": 0.08},
    "room-32-32-4": {"pixel_per_move": 5, "moves": 5, "delay": 0.08}
}


def get_map_name(in_file:str) -> str:
    """Get the map name from the file name

    Args:
        in_file (str): the path of the map file

    Returns:
        str: the name of the map
    """
    return in_file.split("/")[-1].split(".")[0]


class PlanVis:
    """Render MAPF instance
    """
    def __init__(self, in_arg) -> None:

        # Load the yaml file
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
            tmp_config["show_ag_idx"] = in_arg.show_ag_idx

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

        self.map_file:str = tmp_config["map_file"]
        self.scen_file:str = tmp_config["scen_file"]
        self.path_file:str = tmp_config["path_file"]
        self.num_of_agents:int = tmp_config["num_of_agents"]
        self.show_ag_idx:bool = tmp_config["show_ag_idx"]

        self.moves:int = tmp_config["moves"]
        self.tile_size:int = tmp_config["pixel_per_move"]* self.moves
        self.delay:int = tmp_config["delay"]

        self.width:int = -1
        self.height:int = -1
        self.env_map:List[List[bool]] = list()

        self.agents:List = list()
        self.agent_texts:List = list()
        self.start_loc:Dict[int,Tuple[int, int]] = dict()
        self.goal_loc:Dict[int,Tuple[int,int]] = dict()
        self.paths:Dict[int,List[Tuple[int,int]]] = dict()

        self.cur_loc:Dict[int,Tuple[int,int]] = dict()
        self.cur_timestep:int = 0
        self.makespan:int = -1

        self.load_map()
        self.load_paths()
        self.load_agents()

        self.window = Tk()
        wd_width = str(self.width * self.tile_size + 10)
        wd_height = str(self.height * self.tile_size + 60)
        self.window.geometry(wd_width + "x" + wd_height)
        self.window.title("MAPF Instance")

        self.timestep_label = Label(self.window,
                              text = f"Timestep: {self.cur_timestep:03d}",
                              font=("Arial", int(self.tile_size)))
        self.timestep_label.pack(side="top", anchor="ne")

        self.canvas = Canvas(width=self.width * self.tile_size,
                             height=self.height * self.tile_size,
                             bg="white")
        self.canvas.pack(side="bottom", pady=5)
        self.render_env()
        self.render_static_positions(self.goal_loc, "rectangle", "orange")
        self.render_static_positions(self.start_loc, "oval", "yellowgreen")
        self.render_positions()
        self.canvas.update()
        time.sleep(self.delay*4)


    def render_static_positions(self, loc:List=None, shape:str="rectangle", color:str="blue"):
        if loc is None:
            loc = self.cur_loc

        for _ag_ in range(self.num_of_agents):
            if shape == "rectangle":
                self.canvas.create_rectangle(loc[_ag_][0] * self.tile_size,
                                            loc[_ag_][1] * self.tile_size,
                                            (loc[_ag_][0]+1) * self.tile_size,
                                            (loc[_ag_][1]+1) * self.tile_size,
                                            fill=color,
                                            outline="")
            elif shape == "oval":
                self.canvas.create_oval(loc[_ag_][0] * self.tile_size,
                                        loc[_ag_][1] * self.tile_size,
                                        (loc[_ag_][0]+1) * self.tile_size,
                                        (loc[_ag_][1]+1) * self.tile_size,
                                        fill=color,
                                        outline="")
            else:
                logging.error("Undefined shape.")
                sys.exit()

            if self.show_ag_idx:
                self.canvas.create_text((loc[_ag_][0]+0.5)*self.tile_size,
                                        (loc[_ag_][1]+0.5)*self.tile_size,
                                        text=str(_ag_+1),
                                        fill="black",
                                        font=("Arial", int(self.tile_size*0.8)))


    def render_env(self):
        for rid, _cur_row_ in enumerate(self.env_map):
            for cid, _cur_ele_ in enumerate(_cur_row_):
                if _cur_ele_ is False:
                    self.canvas.create_rectangle(cid * self.tile_size,
                                                 rid * self.tile_size,
                                                 (cid+1)*self.tile_size,
                                                 (rid+1)*self.tile_size,
                                                 fill="black")


    def render_positions(self, loc: List = None) -> None:
        if loc is None:
            loc = self.cur_loc

        for _ag_ in range(self.num_of_agents):
            agent = self.canvas.create_oval(loc[_ag_][0] * self.tile_size,
                                            loc[_ag_][1] * self.tile_size,
                                            (loc[_ag_][0]+1) * self.tile_size,
                                            (loc[_ag_][1]+1) * self.tile_size,
                                            fill=COLORS[0],
                                            outline="")
            self.agents.append(agent)

            if self.show_ag_idx:
                ag_idx = self.canvas.create_text((loc[_ag_][0]+0.5)*self.tile_size,
                                                 (loc[_ag_][1]+0.5)*self.tile_size,
                                                 text=str(_ag_+1),
                                                 fill="black",
                                                 font=("Arial", int(self.tile_size*0.8)))
                self.agent_texts.append(ag_idx)


    def load_map(self, map_file:str = None) -> None:
        if map_file is None:
            map_file = self.map_file

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


    def load_agents(self, scen_file:str = None) -> None:
        if scen_file is None:
            scen_file = self.scen_file

        with open(scen_file, "r") as fin:
            fin.readline()  # ignore the first line 'version 1'
            ag_counter:int = 0
            for line in fin.readlines():
                line_seg = line.split('\t')
                self.start_loc[ag_counter] = (int(line_seg[4]), int(line_seg[5]))
                self.cur_loc[ag_counter] = (int(line_seg[4]), int(line_seg[5]))
                self.goal_loc[ag_counter] = (int(line_seg[6]), int(line_seg[7]))

                ag_counter += 1
                if ag_counter == self.num_of_agents:
                    break


    def load_paths(self, path_file:str = None) -> None:
        if path_file is None:
            path_file = self.path_file
        if not os.path.exists(path_file):
            logging.warning("No path file is found!")
            return

        with open(path_file, "r") as fin:
            ag_counter = 0
            for line in fin.readlines():
                ag_idx = int(line.split(" ")[1].split(":")[0])
                self.paths[ag_idx] = list()
                for cur_loc in line.split(" ")[-1].split("->"):
                    if cur_loc == "\n":
                        continue
                    cur_x = int(cur_loc.split(",")[1].split(")")[0])
                    cur_y = int(cur_loc.split(",")[0].split("(")[1])
                    self.paths[ag_idx].append((cur_x, cur_y))
                ag_counter += 1
                if ag_counter == self.num_of_agents:
                    break

            self.num_of_agents = ag_counter

        for ag_idx in range(self.num_of_agents):
            if self.makespan < len(self.paths[ag_idx]):
                self.makespan = len(self.paths[ag_idx])


    def move_agents(self) -> None:
        """Move agents from cur_timstep to cur_timestep+1 and increase the cur_timestep by 1
        """

        while self.cur_timestep < self.makespan:
            self.timestep_label.config(text = f"Timestep: {self.cur_timestep:03d}")

            for _ in range(self.moves):
                for ag_idx, agent in enumerate(self.agents):
                    next_timestep = min(self.cur_timestep+1, len(self.paths[ag_idx])-1)
                    direction = (self.paths[ag_idx][next_timestep][0] - self.cur_loc[ag_idx][0],
                                 self.paths[ag_idx][next_timestep][1] - self.cur_loc[ag_idx][1])
                    cur_move = (direction[0] * (self.tile_size // self.moves),
                                      direction[1] * (self.tile_size // self.moves))
                    self.canvas.move(agent, cur_move[0], cur_move[1])

                    if self.show_ag_idx:
                        self.canvas.move(self.agent_texts[ag_idx], cur_move[0], cur_move[1])

                self.canvas.update()
                time.sleep(self.delay)

            for ag_idx in range(self.num_of_agents):
                next_timestep = min(self.cur_timestep+1, len(self.paths[ag_idx])-1)
                self.cur_loc[ag_idx] = (self.paths[ag_idx][next_timestep][0],
                                        self.paths[ag_idx][next_timestep][1])
            self.cur_timestep += 1
            time.sleep(self.delay * 2)


if __name__ == "__main__":
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
    parser.add_argument('--aid', type=bool, default=False, dest="show_ag_idx",
                        help="Show agent indices or not")
    args = parser.parse_args()

    plan_visualizer = PlanVis(args)
    plan_visualizer.move_agents()
    mainloop()
