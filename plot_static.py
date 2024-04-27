# -*- coding: UTF-8 -*-

import os
from typing import List, Dict
import argparse
from tkinter import Tk, Canvas, mainloop
import json
from util import MAP_CONFIG, Agent, get_map_name, load_map, decode_loc


AGENT_CONFIG = {'color': 'deepskyblue', 'shape': 'oval'}
TASK_CONFIG  = {'color': 'orange', 'shape': 'rectangle'}


class ProblemLoader:
    def __init__(self, prob_dir:str, prob_file:str):
        problem:Dict = {}
        with open(os.path.join(prob_dir, prob_file), mode='r', encoding='utf-8') as fin:
            problem = json.load(fin)
        self.map_file = os.path.join(prob_dir, problem['mapFile'])
        self.agent_file = os.path.join(prob_dir, problem['agentFile'])
        self.team_size = problem['teamSize']
        self.task_file = os.path.join(prob_dir, problem['taskFile'])
        self.reveal_num = problem['numTasksReveal']
        self.strategy = problem['taskAssignmentStrategy']
        self.height, self.width, self.map, _ = load_map(self.map_file)
        self.agents:List[Agent] = []


    def load_agents(self):
        with open(self.agent_file, mode='r', encoding='utf-8') as fin:
            fin.readline()  # Skip the first number
            for line in fin.readlines():
                line = int(line.strip())
                loc = decode_loc(self.width, line)
                # assert self.map[loc[0]][loc[1]] is True
                self.agents.append(Agent(loc))


    def load_tasks(self):
        assert self.strategy == 'roundrobin'
        with open(self.task_file, mode='r', encoding='utf-8') as fin:
            fin.readline()  # Skip the first number
            for (tid, line) in enumerate(fin.readlines()):
                ag_id = tid % self.team_size
                line = int(line.strip())
                loc = decode_loc(self.width, line)
                # assert self.map[loc[0]][loc[1]] is True
                self.agents[ag_id].task_locs.append(loc)


class StaticRenderer:
    """ Render map, agentsm and tasks staticly
    """
    def __init__(self, in_args) -> None:
        self.prob_loader = ProblemLoader(in_args.problemDir, in_args.problemFile)
        self.prob_loader.load_agents()
        self.prob_loader.load_tasks()
        self.tile_size:int = in_args.tileSize
        mname = get_map_name(self.prob_loader.map_file)
        if self.tile_size == -1:
            self.tile_size = MAP_CONFIG[mname]['pixel_per_move'] * \
                MAP_CONFIG[mname]['moves']

        self.window = Tk()
        wd_width:str  = str(self.prob_loader.width  * self.tile_size + 5)
        wd_height:str = str(self.prob_loader.height * self.tile_size + 5)
        self.window.geometry(wd_width + 'x' + wd_height)
        self.window.title(mname)

        self.canvas = Canvas(width=self.prob_loader.width * self.tile_size,
                             height=self.prob_loader.height * self.tile_size,
                             bg='white')
        self.canvas.pack(side='bottom', pady=1)
        print('Done!')


    def render_map(self):
        for rid, _cur_row_ in enumerate(self.prob_loader.map):
            for cid, _cur_ele_ in enumerate(_cur_row_):
                if _cur_ele_ is False:
                    self.canvas.create_rectangle(cid * self.tile_size,
                                                 rid * self.tile_size,
                                                 (cid+1)*self.tile_size,
                                                 (rid+1)*self.tile_size,
                                                 fill='black')


    def render_static_agent(self, ag_idx) -> None:
        agent = self.prob_loader.agents[ag_idx]

        for (tid,task) in enumerate(agent.task_locs):
            self.canvas.create_rectangle(task[1] * self.tile_size,
                                         task[0] * self.tile_size,
                                         (task[1]+1) * self.tile_size,
                                         (task[0]+1) * self.tile_size,
                                         fill=TASK_CONFIG['color'],
                                         outline='')
            self.canvas.create_text((task[1]+0.5) * self.tile_size,
                                    (task[0]+0.5) * self.tile_size,
                                    text=str(tid),
                                    fill='black',
                                    font=('Arial', int(self.tile_size*0.5)))

        self.canvas.create_oval(agent.start_loc[1] * self.tile_size,
                                agent.start_loc[0] * self.tile_size,
                                (agent.start_loc[1]+1) * self.tile_size,
                                (agent.start_loc[0]+1) * self.tile_size,
                                fill = AGENT_CONFIG['color'],
                                outline='')
        self.canvas.create_text((agent.start_loc[1]+0.5)*self.tile_size,
                                (agent.start_loc[0]+0.5)*self.tile_size,
                                text=str(ag_idx),
                                fill='black',
                                font=('Arial', int(self.tile_size*0.5)))


if __name__ == '__main__':
    par = argparse.ArgumentParser(description='Arguments for instacne generator')
    par.add_argument('--problemDir', type=str, default='../random.domain')
    par.add_argument('--problemFile', type=str, default='random.json')
    par.add_argument('--tileSize', type=int, default=-1)
    par.add_argument('--agID', type=int, default=0)
    INPUT_ARGS = par.parse_args()

    static_ren = StaticRenderer(INPUT_ARGS)
    static_ren.render_map()
    static_ren.render_static_agent(INPUT_ARGS.agID)
    mainloop()
