# Sub-optimality Heat-map 

---

## 1  Enabling the Heat-map

| Control                                     | Description                                                                                                                     |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Show Environmental Heatmap** *(checkbox)* | Overlays the *static* heat-map that is pre-computed from the plan file.                                                          |
| **Show Dynamic Heatmap** *(checkbox)*       | Displays a per-timestep *live* map that accumulates while the simulation runs.                                                   |
| **Show Agent Heatmap** *(checkbox)*         | Colours each agent according to its personal sub-optimality score (useful for identifying under-performing agents).              |
| **Heatmap Stats** *(button)*                | Opens a pop-up window with summary statistics (mean, max, standard deviation, and breakdown by sub-optimality type).             |
| **Reset HM** *(button)*                     | Clears the live (dynamic) map so you can start a fresh measurement mid-run.                                                     |
| **Change heatmap view** *(combo box)*       | Focuses on a single component – *All*, *Wrong Direction*, *Wait Actions*, or *Sub-optimal Turns*.                                |


---

## 2  Colour Scale

* Each cell stores an integer **penalty** value.  
  Higher values correspond to hotter colours.
* Colour ramps are auto-normalised unless you start PlanViz with `--heatmap_max <N>`, in which case `N` sets an absolute ceiling.

---

## 3  Underlying Algorithm
For every agent time‑step it compares the agent’s action to a distance oracle 
that estimates remaining path length to the current goal:

Progress check – If the agent fails to reduce its distance to the goal it incurs a penalty:
+1 when it remains at the same distance (wait or lateral step)
+2 when it increases the distance (moves “backwards”)

The penalty is added to the grid‑cell the agent occupies, producing an environment‑level heat‑map of sub‑optimal behaviour.

The penalty is also added to an agent based tracker, allowing the user to visualise under-performing agents.

Rotation assessment – When the action is a turn, the algorithm emulates three one‑step futures (no‑turn, clockwise+forward, counter‑clockwise+forward).
A rotation is penalised (+1) if moving straight would already reduced the distance to the goal, or if the opposite turn would lead to a shorter future distance than the turn actually taken.



* Distance heuristic chosen via `--pathalg` argument in `run.py`:
  * **Auto** – Automatically choose the best tractable heuristic based on grid size
  * **True** – exact shortest-path distances (Dijkstra).  
  * **Landmark** – ALT-style landmark heuristic.  
  * **Manhattan** – fast grid heuristic.


### Static Map

* Constructed once when the plan is loaded (`PlanConfig2024.load_subop_map`).
* Each sub-optimality type is tracked separately:
  1. **Wrong Direction** – a step increases the heuristic distance to the goal.
  2. **Wait Actions** – a `Wait` occurs when a forward move would reduce distance.
  3. **Sub-optimal Turns** – an unnecessary turn or a turn that does not re-orient the agent toward progress.

###  Dynamic Map

* Updated every timestep by `PlanConfig2024.update_dynamic_subop_map()`.

* Penalty rules (per agent, per timestep):
  * **+2** if the next position is farther from the goal than the current one.
  * **+1** for `Wait` actions or unnecessary turns.

## Heatmap Stats

| Field                               | Meaning                                                                                |
| ----------------------------------- |----------------------------------------------------------------------------------------|
| **Non-zero cells**                  | Number of grid squares that have recorded any penalty.                                 |
| **Total penalty**                   | Sum of all cell values.                                                                |
| **Mean / Std dev**                  | Mean/STD of grid cell centric suboptimalities  <br/>Computed over non-zero cells only. |
| **Min / Max**                       | Lowest and highest non-zero cell values.                                               |
| **Wrong Direction / Wait Actions / Sub-optimal Turns** | Global counters for each penalty type.                                                 |
| **Mean / Std per agent**            | Mean/STD of agent centric suboptimalities                                              |

