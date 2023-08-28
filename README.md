# PlanViz
Welcome to PlanViz! This is an **offline** visualization tool for analysing solutions to multi-robot and multi-agent coordination problems.
It is developed as a support tool for participants in the [League of Robot Runners](http://leagueofrobotrunners.org) competition.
However, PlanViz can also be used for a variety of similar problems which are outside the scope of the competition. 

The primary purpose of PlanViz is to better understand how robots/agents move across the map and to offer insights into the errors and events given by the competition [Start-Kit](https://github.com/MAPF-Competition/Start-Kit). Being an offline tool, PlanViz takes as input a grid map and a log file (in `JSON` format) produced by the the competition Start-Kit. The log file describes the planned and executed actions of agents at each timestep and renders the result with [`tkinter`](https://docs.python.org/3/library/tkinter.html), a pyton interface for the Tcl/Tk GUI toolkit (see the `example/warehouse-small.map` and `example/warehouse-small-60.json` for example). An example of the application in action is shown in the following video.

![plan_viz_gif](images/plan_viz.gif)


## Scenario and Visual Markers
The scenario on the left of PlanViz shows how the agents move in the environment and how the tasks are allocated at each timestep.
- The map is plotted in grids with the white ones being the free spaces and black ones being obstacles.
- An agent is plotted in a blue circle, with a number being the agent index and a darkblue dot being its heading.
- A task is plotted in a colored square with a number being the task index. Each task is initially marked in pink, and turns yellowgreen when it is newly assigned to an agent, orange after it is assigned to an agent, and grey when it is completed.
- When PlanViz is in fullsize, right-click an agent to see/hide its path. The paths are presented with a sequence of purple squares, with the locations where the agent rotates or waits being larger.

![scenario](images/scenario.png)

## User Interface
The user interface provides operations for user to control the scenario.
- `Timestep` shows the current timestep.
- The buttons controls the progress of the plan/execution:
    - `Play`: Auto-play the plan/execution
    - `Pause`: Pausee the scenario to the current timestep
    - `Fullsize`: Reset the scenario to fullsize
    - `Next`: Move the scenario to the next timestep
    - `Prev`: Move the scenario to the previous timestep
    - `Reset`: Reset the scenario to timestep 0
- The checkbox controls what to be shown in the scenario.
- `Start timestep`: Input the desire start timestep and move the scenario to.
- `List of errors` contains collisions and timeout issues from the Start-Kit. When the scenario is paused, you can double-click an error to see the invalid movements.
- A vertex/edge collision between agents $a_i$ and $a_j$ at location $V$/edge $(U,V)$ at timestep $T$ is presented under the format of `ai, aj, v=V/e=(U,V), t=T`. Single-click the collision in `List of errors` can mark the colliding agents in red, and press `ctrl` while clicking to select multiple collisions. See agents 19 and 22 in the following figure for example.
- `List of events` contains information of task assignments and task completion. When the scenario is paused, you can *double-click* an event to move all the agents to one timestep before such event occurs.

## Arguments
- `--map` (type: *str*): Path to the map file (ends with `.map`). See `example/warehouse-small.map` for more information.
- `--plan` (type: *str*): Path to the planned path file (ends with `.json`). See `example/warehouse-small-60.json` for more information.
- `--n` (type: *int*): Number of agents need to show, starting from index 0 (*default*: All agents in the path file).
- `--grid`: Whether to show the grids on the map. Set to True if specified.
- `--aid`: Whether to show the agent indices. Set to True if specified.
- `--tid`: Whether to show the task indices. Set to True if specified.
- `--static`: Whether to show the start locations. Set to True if specified.
- `--ca`: Whether to mark all the colliding agents in red. Set to True if specified.
- `--ppm` (type: *int*):  Number of pixels per move, depending on the size of the map.
- `--mv` (type: *int*):  Number of moves per timestep; the tile size of the map is `ppm` $\times$ `mv`.
- `--delay` (type: *float*):  Wait time for each timestep after agents' movements.
- `--start` (type: *int*): Start timestep for visualization (*default*: 0).
- `--end` (type: *int*): End timestep for visualization (*default*: 100).

If one is using [our maps](https://github.com/MAPF-Competition/benchmark_problems),
then we have default values for `ppm`, `mv`, and `delay`, so the user does not need to specify them.

## Run
To run PlanViz, open a terminal under the directory `PlanViz/script` and type the following example command:
```bash
python3 plan_viz.py --map ../example/warehouse_small.map --plan ../example/warehouse_small.json --grid --aid --static --ca
```

