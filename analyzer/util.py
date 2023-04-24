#! /home/rdaneel/anaconda3/lib/python3.8
# -*- coding: UTF-8 -*-
"""Utility functions"""

import logging
import os
import sys
from typing import List, Tuple
import random
import pandas as pd
import numpy as np


def read_file(in_path:str) -> pd.DataFrame:
    """ Read the csv file with pandas

    Args:
        in_path (str): path to the csv file

    Returns:
        pd.DataFrame: the csv file
    """
    if not os.path.exists(in_path):
        logging.error('%s does not exist!', in_path)
        sys.exit()
    else:
        return pd.read_csv(in_path)


def get_file_dir(exp_path:str, map_name:str, solver_name:str) -> str:
    """Get the path to the csv files

    Args:
        exp_path (str): path to the whole experiments
        map_name (str): map name
        solver_name (str): solver name

    Returns:
        str: path to the csv files
    """
    map_dir = os.path.join(exp_path, map_name)
    out_dir = os.path.join(map_dir, solver_name)
    return out_dir


def get_file_name(map_name:str, scen:str, ag_num:int, solver_name: str) -> str:
    """Get the name of the csv file (end with .csv)

    Args:
        map_name (str): map_name
        scen (str): even or random scen
        ag_num (int): number of agents
        solver_name (str): the solver name
    Returns:
        str: name of the csv files
    """
    out_name = map_name + '-' + scen + '-' + str(ag_num) + '-' + solver_name + '.csv'
    return out_name


def get_csv_instance(exp_path:str, map_name:str, scen:str, ag_num:int, 
                     solver_name:str, solver_dir_name:str=None):
    """Get the path and read the csv with pandas

    Args:
        map_name (str): map_name
        scen (str): even or random scen
        ag_num (int): number of agents
        solver_name (str): the solver name from config.yaml
        solver_dir_name (str): the name of the directory where the solver saves
    Returns:
        pd.DataFrame: the csv file
    """
    if solver_dir_name is None:
        solver_dir_name = solver_name
    return read_file(os.path.join(
        get_file_dir(exp_path, map_name, solver_dir_name),
        get_file_name(map_name, scen, ag_num, solver_name)))


def create_csv_file(exp_path:str, map_name:str, scen:str, ag_num:int, ins_num:int, sol_dir:str,
                    sol_names:List[str], mode:str='min', objective:str='runtime'):
    csv_files = dict()
    for idx, _name_ in enumerate(sol_names):
        csv_files[_name_] = get_csv_instance(exp_path, map_name, scen, ag_num, _name_, sol_dir)
        if idx == 0:
            first_name = _name_

    # Sort the csv_files accroding to the objective
    buffer = dict()
    for col in csv_files[first_name].columns:
        buffer[col] = list()

    target_idx = -np.inf
    if mode == 'min':
        target_idx = 0
    elif mode == 'mid':
        target_idx = len(sol_names)//2 - 1
    elif mode == 'max':
        target_idx = len(sol_names) - 1

    for idx in range(ins_num):
        tmp_rows = dict()
        tmp_objs = dict()
        for _name_, _file_ in csv_files.items():
            row = _file_.iloc[idx]
            tmp_rows[_name_] = row
            tmp_objs[_name_] = row[objective]

        sorted_objs = dict(sorted(tmp_objs.items(), key=lambda item : item[1]))
        for j, val in enumerate(sorted_objs.items()):
            if j == target_idx:
                tmp_row_val = tmp_rows[val[0]]
                for _k_ in buffer.keys():
                    buffer[_k_].append(tmp_row_val[_k_])
                break

    solver_type = sol_names[0].split('_')[0]
    out_dir = exp_path + map_name + '/' + solver_type + '_' + mode + '_' + objective
    if not os.path.exists(out_dir):  # Create a new directory because it does not exist
        os.makedirs(out_dir)

    out_file_name = map_name + '-' + scen + '-' + str(ag_num) + '-' + \
        solver_type + '_' + mode + '_' + objective + '.csv'
    out_df = pd.DataFrame(buffer)
    out_df.to_csv(path_or_buf=os.path.join(out_dir, out_file_name), index=False)


def load_map(map_file:str):
    """load map from the map_file
        Args:
            map_file (str): file of the map
    """
    height = -1
    width = -1
    out_map = []
    with open(map_file, mode="r", encoding="UTF-8") as fin:
        fin.readline()  # Skip the first line
        height = int(fin.readline().strip("\n").split(" ")[-1])
        width  = int(fin.readline().strip("\n").split(" ")[-1])
        fin.readline()  # Skip the line "map"
        for line in fin.readlines():
            line = line.strip("\n").split("")
            out_line = [_char_ == "." for _char_ in line]
            out_map.append(out_line)

    return height, width, out_map


def random_walk(in_map:List[List[bool]], init_loc:Tuple, steps:int):
    """Random walk from the init_loc on in_map with steps

    Args:
        in_map (List[List[bool]]): map
        init_loc (Tuple): initial location of the agent
        steps (int): number of steps to move
    """
    if in_map[init_loc[0]][init_loc[1]] is False:
        logging.error("location (%d,%d) should be a free space!", init_loc[0], init_loc[1])
        sys.exit()

    curr_loc = init_loc
    height = len(in_map)
    width = len(in_map[0])
    for _ in range(steps):
        next_locs = [(curr_loc[0]+1, curr_loc[1]),
                     (curr_loc[0]-1, curr_loc[1]),
                     (curr_loc[0], curr_loc[1]+1),
                     (curr_loc[0], curr_loc[1]-1)]
        random.shuffle(next_locs)

        for next_loc in next_locs:
            if  -1 < next_loc[0] < height and\
                -1 < next_loc[1] < width and\
                in_map[next_loc[0]][next_loc[1]] is True:
                curr_loc = next_loc
                break
    return curr_loc
    