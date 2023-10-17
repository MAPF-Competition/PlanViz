import pandas as pd
import json
import argparse

class TrackerTransfer:
    """ Transfer the tracker data into 'robotrunner' output style
    """
    def __init__(self, scen_file, plan_file):
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
        self.num_task_finished = self.team_size
    
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

def runSingleTransfer(scen_file, plan_file, output_file):
    tracker_transfer = TrackerTransfer(scen_file,plan_file)
    tracker_transfer.read_single_plan(0)
    tracker_transfer.read_start_task()
    tracker_transfer.write_to_json(output_file)

# def runMultiTransfer(random_scen,even_scen,plan_file,output_file):
#     muti_plan_df = pd.read_csv(plan_file)
#     if random_scen == None:
#         print("random scenario file missing, may lose some records")
#     if even_scen == None:
#         print("even scenario file missing, may lose some records")
#     success_count = 0
#     for index, row in muti_plan_df.iterrows():
#         success_count+=1
#     print(success_count)
#         #print(row['solution_plan'])
#         # print("------- transfering solution for the",str(index)+"th","instance -------")
#         # if row['scen_type'] == 'even':
#         #     if even_scen == None:
#         #         print("fail due to even scenario file missing")
#         #         continue
#         #     TrackerTransfer = TrackerTransfer(even_scen,plan_file)

        


def main() -> None:
    """The main function of the tracker transfer.
    """
    parser = argparse.ArgumentParser(description='A program to transfer results from mapf tracker to visualiser support format')

    parser.add_argument('--plan', type=str, help="Path to the planned path file")
    #parser.add_argument('--randomScen', type=str, help="Path to random scenario file")
    #parser.add_argument('--evenScen', type=str, help="Path to even scenario file")
    #parser.add_argument('--multiPlan',action="store_true", help="Enable this if the plan file contains path for multiple instances")
    parser.add_argument('--scen', type=str, help="Path to scenario file")
    parser.add_argument('--outputFile', type=str, default="../example/transfer_result.json", help="Path to the output file (should be json file)")
    args = parser.parse_args()

    if args.plan == None:
        raise TypeError("Missing variable: plan (path the the planned path file).")
    plan = args.plan
    output = args.outputFile
    if args.scen == None:
        raise TypeError("Missing variable: scen (path to scenario file).")
    scen = args.scen
    runSingleTransfer(scen,plan,output)

    #multi = args.multiPlan
    #if not multi:
        # if args.randomScen == None and args.evenScen == None:
        #     raise TypeError("Missing variable: scenario file (either randomScen or evenScen).")
        # if args.randomScen != None and args.evenScen != None:
        #     raise TypeError("More then one scenario file provide: when set singlePlan to True, there should be only one scenario file, either randomScen or evenScen.")
        # if args.randomScen != None:
        #     scen = args.randomScen
        # elif args.evenScen != None:
        #     scen = args.evenScen
        # output = output+".json"
        # runSingleTransfer(scen,plan,output)
    # else:
    #     if args.randomScen == None and args.evenScen == None:
    #         raise TypeError("Missing variable: should provide at least one from randomScen and evenScen.")
    #     random_scen = args.randomScen
    #     even_scen = args.evenScen
    #     runMultiTransfer(random_scen, even_scen,plan,output)

if __name__ == "__main__":
    main()

