import pandas as pd
import json

class TrackerTransfer:
    """ Transfer the tracker data into 'robotrunner' output style
    """
    def __init__(self, map_file, scen_file, plan_file):
        self.map_file = map_file
        self.scen_file = scen_file
        self.plan_file = plan_file
        
        self.action_model = "MAPF"
        self.all_valid = "Yes"
        self.team_size = 0
        self.start = []
        self.num_task_finished = 0
        self.sum_of_cost = 0
        self.makespan = 0
        self.actual_path = []
        self.planner_path = []
        self.plannerTime = []
        self.errors = []
        self.events = []
        self.tasks = []

    def read_single_plan(self,row):
        plan_df = pd.read_csv(self.plan_file)
        self.team_size = int(plan_df['agents'][row])
        self.sum_of_cost = int(plan_df['solution_cost'][row])
        plan = plan_df['path'][row].split('\n')
        for path in plan:
            if (len(path) > self.makespan):
                self.makespan = len(path) 
            self.actual_path.append(list(path.upper()))
            self.planner_path.append(list(path.upper()))
            event = []
            event.append([len(self.events),0,"assigned"])
            event.append([len(self.events),len(path),"finished"])
            self.events.append(event)
        self.fill_path()
    
    def read_start_task(self):
        """ read start and task from scen file
        """
        f = open(self.scen_file)
        line = f.readline() #skip the first line
        line = f.readline()
        while line:
            line = line.split()
            start_row = int(line[5])
            start_col = int(line[4])
            task_row = int(line[7])
            task_col = int(line[6])
            self.start.append([start_row,start_col,'N'])
            self.tasks.append([len(self.tasks),task_row,task_col])
            line = f.readline()

    def fill_path(self):
        for agent in range(self.team_size):
            curr_len = int(len(self.actual_path[agent]))
            for i in range(curr_len,self.makespan):
                self.actual_path[agent].append('W')
                self.planner_path[agent].append('W')
            if (len(self.planner_path[agent]) != self.makespan or len(self.actual_path[agent]) != self.makespan):
                print("wrong")
            self.actual_path[agent] = ",".join(self.actual_path[agent])
            self.planner_path[agent] = ",".join(self.planner_path[agent])
        
            
    
    def write_to_json(self, write_file):
        output_dic = dict()
        output_dic['actionModel'] = self.action_model
        output_dic['AllValid'] = self.all_valid
        output_dic['teamSize'] = self.team_size
        output_dic['start'] = self.start
        output_dic['numTaskFinished'] = self.num_task_finished
        output_dic['sumOfCost'] = self.sum_of_cost
        output_dic['makespan'] = self.makespan
        output_dic['actualPaths'] = self.actual_path
        output_dic['plannerPaths'] = self.planner_path
        output_dic['plannerTimes'] = self.plannerTime
        output_dic['errors'] = self.errors
        output_dic['events'] = self.events
        output_dic['tasks'] = self.tasks
        with open(write_file,"w") as f:
            json.dump(output_dic,f, indent=4)



temp = TrackerTransfer("../example/random-32-32-20.map", "../example/random-32-32-20-random-1.scen", "../example/random-32-32-20_random_1_300.csv")
temp.read_single_plan(0)
temp.read_start_task()
temp.write_to_json("test.json")
