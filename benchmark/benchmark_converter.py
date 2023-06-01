# -*- coding: UTF-8 -*-
"""Benchmark converter
Convert the MAPF instances in MAPF benchmark suite to task files
"""

import os
import sys
import logging
import argparse
from typing import List, Tuple, Dict
import yaml


class BenchmarkConverter:
    """Class for benchmark converter
    Input the map, the scens (either scen-even or scen-random), the number of agents,
    and the number of tasks. The converter will start from the first row of the scen.
    """

    def __init__(self, input_arg) -> None:
        print("===== Initialize Benchmark Converter =====")

        self.start_loc:Dict[int, int] = {}     # Agent -> location
        self.tasks:List[int]  = []  # all the tasks

        # Load the yaml file or the input arguments
        self.config: Dict = {}

        if input_arg.config is not None:
            config_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), input_arg.config)
            with open(config_dir, mode="r", encoding="utf-8") as fin:
                self.config = yaml.load(fin, Loader=yaml.FullLoader)
        else:
            self.config["data_path"]:str = input_arg.data_path
            self.config["map_name"]:str = input_arg.map_name
            self.config["scen_name"]:str = input_arg.scen_name
            self.config["num_of_agents"] = input_arg.num_of_agents

            if input_arg.agent_file is not None:
                self.config["agent_file"] = input_arg.agent_file
            if input_arg.task_file is not None:
                self.config["task_file"]  = input_arg.task_file
            if input_arg.num_of_tasks is not None:
                self.config["num_of_tasks"] = input_arg.num_of_tasks

        # Set the default values in self.config
        assert self.config["num_of_agents"] is not None

        if "num_of_tasks" not in self.config.keys():
            self.config["num_of_tasks"] = -1  # put all goal locations into the task

        if "ins_id" not in self.config.keys():
            self.config["ins_id"]:List[int] = [i+1 for i in range(25)]  # from 1 to 25

        if "agent_file" not in self.config.keys():
            self.config["agent_file"] = "./" + self.config["map_name"] + "_" +\
                self.config["scen_name"] + "_" + str(self.config["num_of_agents"]) + "_agents.txt"
        if "task_file" not in self.config.keys():
            self.config["task_file"] = "./" + self.config["map_name"] + "_" +\
                self.config["scen_name"] + "_" + str(self.config["num_of_agents"]) + "_tasks.txt"

        assert self.config["num_of_agents"] > 0
        assert self.config["num_of_tasks"] > -2


    def load_map_size(self):
        map_fn = "mapf-map/" + self.config["map_name"] + ".map"
        map_file = os.path.join(self.config["data_path"], map_fn)
        print("Get the size of map " + self.config["map_name"])

        if not os.path.exists(map_file):
            logging.error("\nNo map file is found!")
            sys.exit()

        with open(map_file, mode="r", encoding="utf-8") as fin:
            fin.readline()  # ignore "type"
            self.config["height"] = int(fin.readline().strip().split(' ')[1])
            self.config["width"]  = int(fin.readline().strip().split(' ')[1])


    def load_locations(self) -> List[Tuple[int,int]]:
        self.load_map_size()  # Add map width and height to self.config
        assert "height" in self.config.keys() and self.config["height"] > 0
        assert "width"  in self.config.keys() and self.config["width"] > 0

        output_loc:List[Tuple[int,int]] = []
        scen_dir = os.path.join(self.config["data_path"], "scen-" + self.config["scen_name"])
        for _ins_idx_ in self.config["ins_id"]:
            scen_fn = self.config["map_name"] + "-" + self.config["scen_name"] +\
                "-" + str(_ins_idx_) + ".scen"
            scen_file = os.path.join(scen_dir, scen_fn)
            if not os.path.exists(scen_file):
                logging.error("\nNo scen path is found!")
                sys.exit()

            with open(scen_file, mode="r", encoding="utf-8") as fin:
                head:str = fin.readline().rstrip("\n").split(" ")[0]  # ignore the first line
                assert head == "version"  # we only process files from the MAPF suite
                for line in fin.readlines():
                    line_seg = line.split("\t")
                    cur_start:int = int(line_seg[5]) * self.config["width"] + int(line_seg[4])
                    cur_goal:int  = int(line_seg[7]) * self.config["width"] + int(line_seg[6])
                    output_loc.append((cur_start, cur_goal))

        return output_loc


    def generate_txt(self):
        assert self.config["num_of_agents"] == len(self.start_loc)
        with open(self.config["agent_file"], mode="w", encoding="utf-8") as fout:
            fout.write(str(self.config["num_of_agents"]) + "\n")
            for aid in range(self.config["num_of_agents"]):
                fout.write(str(self.start_loc[aid]) + "\n")

        with open(self.config["task_file"], mode="w", encoding="utf-8") as fout:
            fout.write(str(len(self.tasks)) + "\n")
            for cur_task in self.tasks:
                fout.write(str(cur_task) + "\n")


    def convert_to_tasks(self):
        all_locations:List[Tuple[int,int]] = self.load_locations()
        num_all_locs = len(all_locations)
        agent_tasks:Dict[int,List[int]] = {}

        # Generate start locations and the initial tasks, one for each agent
        for aid in range(self.config["num_of_agents"]):
            cur_loc:Tuple[int,int] = all_locations.pop(0)
            self.start_loc[aid]:int = cur_loc[0]
            agent_tasks[aid] = [cur_loc[1]]
        assert len(all_locations) + self.config["num_of_agents"] == num_all_locs

        # Generate other tasks from all_locations
        ag_cnt = 0
        for (sloc, gloc) in all_locations:
            aid = ag_cnt % self.config["num_of_agents"]
            agent_tasks[aid].append(sloc)
            agent_tasks[aid].append(gloc)
            ag_cnt += 1

        # Collect the tasks in a round robin order
        has_task:List[bool] = [True for _ in range(self.config["num_of_agents"])]
        ag_cnt = 0
        while any(has_task):
            aid = ag_cnt % self.config["num_of_agents"]
            if agent_tasks[aid]:  # There is still elements in the list
                self.tasks.append(agent_tasks[aid].pop(0))
            else:
                has_task[aid] = False
            ag_cnt += 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Take config.yaml as input!")
    parser.add_argument("--config", type=str, default=None, help="configuration file")
    parser.add_argument("--data_path", type=str, default="./", help="path to the MAPF benchmark")
    parser.add_argument("--map_name", type=str, default="random-32-32-20", help="map name")
    parser.add_argument("--scen_name", type=str, default="even", help="scen name")
    parser.add_argument("--agent_file", type=str, default=None, help="output agent file")
    parser.add_argument("--task_file", type=str, default=None, help="output task file")
    parser.add_argument("--num_of_agents", type=int, default=None, help="number of agents")
    parser.add_argument("--num_of_tasks", type=str, default=None, help="number of tasks")
    args = parser.parse_args()

    benchmark_converter = BenchmarkConverter(input_arg=args)
    benchmark_converter.convert_to_tasks()
    benchmark_converter.generate_txt()
