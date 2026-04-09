# PlanViz
The primary purpose of PlanViz is to help participants in the [League of Robot Runners competition](https://leagueofrobotrunners.org) better understand the planned paths and executed commands of their robots. PlanViz offers insights into problem solving strategies, by showing how robots move across the map, and by highlighting and exploring the errors and events given by the competition [Start-Kit](https://github.com/MAPF-Competition/Start-Kit). 

Being an offline tool, PlanViz takes as input a grid map (part of the competition problem set) and a [`JSON` formatted log file](https://github.com/MAPF-Competition/Start-Kit/blob/main/Input_Output_Format.md), which is produced by the the competition Start-Kit. For the 2024/2026 view, the log file describes the planned and executed actions of agents over time, where time is shown as the elapsed timeline index. An example of the application in action is shown in the following video.

![plan_viz_gif](images/plan_viz2026.gif)

## Visual Markers

PlanViz provides a variety of visual markers to help users understand the results of their planning strategies.

![scenario](images/scenario_2.png)

- The map is plotted in grids with the white ones being the free spaces and black ones being obstacles.
- An agent is plotted in a blue circle, with a number being the agent index and a darkblue dot being its heading. When `delayIntervals` are present in a `2026 LoRR` file, delayed agents are shown in yellow during the corresponding ticks.
- All errands of tasks are represented by colored squares. Errands for a task are initially marked in yellow, turn orange when the task is assigned to an agent, and turn to white once the errand is completed and there is no further errand at this location.

![scenario](images/scenario_1.png)

- Right-click an agent to see/hide its path. The paths are presented with a sequence of purple squares, with the locations where the agent rotates or waits being larger.
- Right-clicking on non-agent grids will cancel all agents selections.

![scenario](images/scenario_4.png)

- Ctrl + Right-click an errand will show all related events
- Right-clicking on white grids will cancel selection.


## UI Options and Controls

The user interface supports a variety of operations to control and focus the display of plans.

- In the 2024/2026 UI, `Time` shows the current time.
- The buttons controls the progress of the plan/execution:
  - `Play`: Auto-play the plan/execution
  - `Pause`: Pause the scenario at the current time
  - `Fullsize`: Reset the scenario to fullsize
  - `Next`: Move the scenario to the next time
  - `Prev`: Move the scenario to the previous time
  - `Restart`: Reset the scenario to time 0
- The checkbox controls what to be shown in the scenario.
- In the 2024/2026 UI, `Start time`: Input the desired start time and move the scenario to it.
- `List of errors` contains collisions and timeout issues from the Start-Kit. When the scenario is paused, you can double-click an error to see the invalid movements.
- A vertex/edge collision between agents $a_i$ and $a_j$ at location $V$/edge $(U,V)$ at time $T$ is presented under the format of `ai, aj, v=V/e=(U,V), t=T`. Single-click the collision in `List of errors` can mark the colliding agents in red, and press `ctrl` while clicking to select multiple collisions. See agents 19 and 22 in the following figure for example.
- `Most recent events` contains information of task assignments, errands completion and task completion. When the scenario is paused, you can *double-click* an event to move all the agents to the time when such event occurs.

## Arguments

- `--map` (type: *str*): Path to the map file (ends with `.map`). See `example/warehouse-small.map` for more information.
- `--plan` (type: *str*): Path to the planned path file (ends with `.json`). See `example/warehouse-small-60.json` for more information.
- `--n` (type: *int*): Number of agents to show, starting from index 0 (*default*: All agents in the path file).
- `--grid` (type: *bool*): Whether to show the grids on the map (*default*: True).
- `--aid` (type: *bool*): Whether to show the agent indices (*default*: True).
- `--tid` (type: *bool*): Whether to show the task indices (*default*: False).
- `--static`: Whether to show the start locations (*default*: False). Set to True if specified.
- `--ca`: Whether to mark all the colliding agents in red (*default*: False). Set to True if specified.
- `--ppm` (type: *int*): Number of pixels per move, depending on the size of the map (*default*: auto-configured per map).
- `--mv` (type: *int*): Number of moves per action; the tile size of the map is `ppm` $\times$ `mv` (*default*: auto-configured per map).
- `--delay` (type: *float*): Wait time between animation updates (*default*: auto-configured per map).
- `--start` (type: *int*): Start time for visualization (*default*: 0).
- `--end` (type: *int*): End time for visualization (*default*: inf).
- `--hm` (type: *List[str]*): A list of path files (ends with `.json`) for generating heatmap.
- `--pathalg` (type: *str*) Distance heuristic used for suboptimality heatmap (see Heatmap.md)
- `--heatmap_max` (type: *int*) Heatmap colour ramp ceiling (*default*: -1 = relative scaling)
- `--version` (type: *str*): Plan file version. Supported values: `'2024 LoRR'`, `'2026 LoRR'`, or `'2023 LoRR'`. If not specified, the version is read from the plan JSON file. If neither is available, defaults to `2023 LoRR` (*default*: None).
- `--window` (type: *int*): Number of timesteps to load from the start time. The visualization will cover timesteps from `start` to `start + window` (*default*: 50000).
- `--event-limit` (type: *int*): Number of recent events to show in the event panel (*default*: 10).

If one is using [our maps](https://github.com/MAPF-Competition/benchmark_problems),
then we have default values for `ppm`, `mv`, and `delay`, so the user does not need to specify them.

## Run

To run PlanViz, open a terminal under the directory `PlanViz/` and type the following example command:

```bash
python script/run.py --map example/warehouse_small.map --plan example/warehouse_small_2026.json
```

Please keep in mind the formats of `JSON` files are different between 2023, 2024, and 2026.
