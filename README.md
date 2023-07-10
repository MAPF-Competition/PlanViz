# PlanViz
Welcome to PlanViz! This is an **offline** visualization tool that shows not only the agents' movements but also the errors and events given by the [Start-Kit](https://github.com/MAPF-Competition/Start-Kit). Our goal is to use PlanViz for not only visualization but also debugging.
PlanViz takes the map and the output file (in `JSON` format) from the Start-Kit as inputs and renders with `tkinter` that contains the scenario and the user interface, as shown in the following video.

![plan_viz_gif](images/plan_viz.gif)


## Properties
### Scenario
The scenario on the right of PlanViz shows how the agents move in the environment and how the tasks are allocated at each timestep.
- The map is plotted in grids with the white ones being the free spaces and black ones being obstacles.
- An agent is plotted in a blue circle, with a number being the agent index and a darkblue dot being its heading.
- A task is plotted in a colored square with a number being the task index. Each task is initially marked in orange, and turns pink when it is assigned to an agent and grey when it is completed.
- When PlanViz is in fullsize, right-click an agent to see/hide its path. The paths are presented with a sequence of purple squares, with the locations where the agent rotates or waits being larger.

### User Interface
The user interface provides operations for user to control the scenario.
- `Timestep` shows the current timestep.
- The buttons controls the progress of the plan/execution:
    - `Play`: Auto-play the plan/execution
    - `Pause`: Pausee the scenario to the current timestep
    - `Fullsize`: Reset the scenario to fullsize
    - `Next`: Move the scenario to the next timestep
    - `Prev`: Move the scenario to the previous timestep
    - `Reset`: Reset the scenario to timestep 0
- The checkbox controls what to be shown in the scenario:
- `Start timestep`: Input the desire start timestep and move the scenario to that.
- `Current mode`: Switch the path between the planner (i.e., the plan from the Start-Kit) and the executer (i.e., the simulator).
- `List of errors` contains collisions and timeout issues from the Start-Kit. Double-click an error to move all the agents to one timestep before such error occurs.
- A vertex/edge collision between agents $a_i$ and $a_j$ at location $V$/edge $(U,V)$ at timestep $T$ is presented under the format of `ai, aj, v=V/e=(U,V), t=T`. Single-click the collision in `List of errors` can mark the colliding agents in red, and press `ctrl` while clicking to select multiple collisions. See agents 19 and 22 in the following figure for example.
- `List of events` contains information of task assignments and task completion. Double-click an event to move all the agents to one timestep before such event occurs.

![scenario](images/scenario.png)


## Arguments
- `--map` (type: *str*): Path to the map file (ends with `.map`). See `example/maze-32-32-2.map` for more details.
- `--plan` (type: *str*): Path to the planned path file (ends with `.path`). See `example/result.path` for more details.
- `--n` (type: *int*): Number of agents need to show (*default*: All agents in the path file)
- `--grid`: Whether to show the grids on the map. Set to True if specified.
- `--aid`: Whether to show the agent indices. Set to True if specified.
- `--tid`: Whether to show the task indices. Set to True if specified.
- `--static`: Whether to show the start locations. Set to True if specified.
- `--ca`: Whether to mark all the colliding agents in red. Set to True if specified.
- `--ppm` (type: *int*):  Number of pixels per move, depending on the size of the map
- `--mv` (type: *int*):  Number of moves per timestep; the tile size of the map is `ppm` $\times$ `mv`.
- `--delay` (type: *float*):  Wait time for each timestep

If one is using [our maps](https://github.com/MAPF-Competition/benchmark_problems),
then we have default values for `ppm`, `mv`, and `delay`, so the user does not need to specify them.

## Run
To run PlanViz, open a terminal under the directory `MAPF_analysis/visualizer and type the following example command:
```bash
python plan_viz.py --map ./warehouse-small.map --plan ./warehouse-small-60.json --grid --aid --static --ca
```

