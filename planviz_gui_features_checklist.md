# PlanViz GUI – Feature Summary & Regression Checklist

This document summarizes the **PlanViz** GUI features found in:

- `run.py` (CLI entry point / version switch)
- `plan_config.py` (data loading + canvas rendering)
- `plan_viz.py` (control panel UI + user interactions)
- `util.py` (colors, motion model, helper classes)
- `paths_transfer.py`, `tracker_transfer.py` (optional: convert external outputs into PlanViz JSON)

---

## 1) What this GUI does (high-level)

PlanViz is a **Tkinter-based visualizer** for multi-agent plans on a grid map:

- Loads a **MovingAI-style `.map`** file and a **PlanViz JSON plan** file.
- Renders the environment (obstacles + coordinates) on a `tk.Canvas`.
- Renders agents (and optionally their orientations), tasks, conflicts/errors, and events.
- Provides playback controls (play/pause/step/jump), overlays, and inspection tools.

Two UI generations exist:

- **PlanViz2023** (plan file version `"2023 LoRR"` or default)
- **PlanViz2024** (plan file version `"2024 LoRR"`)

---

## 2) Module map (where to look in code)

### Startup / wiring
- **`run.py`**
  - Reads `--map` and `--plan`
  - Detects plan `version` from JSON (or `--version`)
  - Creates `PlanConfig2023/2024` then `PlanViz2023/2024`
  - Starts `tk.mainloop()`

### Data loading + rendering primitives
- **`plan_config.py`**
  - `PlanConfig2023`: loads map, paths, tasks, events, errors, plus optional overlays:
    - heatmap (`--hm`)
    - highway (`--hw`)
    - search trees (`--searchTree`)
    - heuristic map (`--heu`)
  - `PlanConfig2024`: loads map, paths, sequential tasks, schedule, events, errors.

### GUI controls + interaction logic
- **`plan_viz.py`**
  - `PlanViz2023`: control panel, playback, toggles, listboxes, right-click agent path
  - `PlanViz2024`: improved click logic, pop-up window, hover display, errands/task sequences

### Shared types + motion model
- **`util.py`**
  - Color constants, motion model (`state_transition*`), object wrappers (`Agent`, `Task`, `SequentialTask`)

---

## 3) UI feature inventory

### 3.1 Features common to both 2023 + 2024

**Canvas view**
- Environment grid with obstacles (black cells)
- Coordinate labels on right/bottom borders
- Agents (circles); optional direction dot for `actionModel == "MAPF_T"`
- Zoom with mouse wheel; pan by mouse drag
- “Fullsize” button resets zoom

**Time controls**
- **Play**: continuous animation (until makespan/end)
- **Pause**: stops playback
- **Next / Prev**: step forward/back one timestep
- **Restart/Reset**: jump back to start timestep and clear selections
- **Start timestep + Go**: jump to arbitrary timestep (re-renders agent objects)

**Display toggles**
- Show/hide grids
- Show/hide agent indices
- Show/hide start locations
- Show colliding agents (agents involved in errors become red)

**Inspection panels**
- Conflict/Error list (select to highlight, double-click to jump)
- Event list (double-click to jump)

---

### 3.2 PlanViz2023-specific features

**Task visualization**
- Tasks are single-location rectangles with color-coded state:
  - unassigned / newlyassigned / assigned / finished
- **Task filter combobox**: `all | unassigned | newlyassigned | assigned | finished | none`
- **Show task indices** checkbox

**Overlays (require CLI inputs in `run.py`)**
- Heatmap overlay (`--hm ...`) from additional plan files
- Highway overlay (`--hw highway.txt`)
- Heuristic overlay (`--heu heuristics.csv`)
- Search tree overlay (`--searchTree tree.csv ...`) + combobox to select which tree to show

**Agent path inspection**
- Right-click an agent to toggle its (execution) path rectangles
- When one or more agents are selected, tasks can be filtered to only those agents’ tasks

**Conflict jump visualization**
- Double-click a conflict: jumps to just before the conflict, briefly animates planned motion vs executed motion.

---

### 3.3 PlanViz2024-specific features

**Sequential tasks / errands**
- Each *task id* may contain multiple locations (“errands”).
- UI can highlight the **next errand** per agent and draw arrows connecting errands.

**Task visibility modes**
- Combobox values: `Next Errand | Assigned Tasks | All Tasks`

**Agent interaction model**
- **Left-click** on an agent:
  - highlights that agent’s next errands (orange/pink coloring)
  - optionally shows the agent’s path (depends on “Show selected agent path” checkbox)
  - draws arrows from agent → next errands
- **Left-click empty space** clears selection (if not running)

**Hover tooling**
- Mouse coordinate label updates continuously
- Optional “Show location when mouse hover” draws a red `(x,y)` label on the hovered cell

**Popup inspector**
- Right-click (or left-click on occupied cell) opens a popup window containing:
  - Agent events at that location
  - Tasks at that location
- Double-click a popup entry to jump time and highlight relevant agent/tasks

**Performance**
- Agent path rectangles are **lazy-rendered** (created only when needed).

---

## 4) Plan JSON “sanity checklist” (most common reason features “don’t show”)

### 4.1 2023 plan file (expected keys)
Minimum keys used:
- `teamSize`, `makespan`, `actionModel`
- `start`: list of `[row, col, direction]`
- `actualPaths`, `plannerPaths`
- `events` (needed for task states + event list)
- `tasks` (task locations)

Optional:
- `errors` (conflict list)

### 4.2 2024 plan file (expected keys)
Minimum keys used:
- `version`: `"2024 LoRR"`
- `teamSize`, `makespan`, `actionModel`
- `start`, `actualPaths`, `plannerPaths`
- `tasks`: each entry includes a release time and multiple locations
- `events` (finish events)
- `errors` and `scheduleErrors` (should exist even if empty)

Optional:
- `actualSchedule` (enables assignment events + better agent timeline)

---

## 5) Manual regression checklist (copy/paste)

### A. Launch / startup
- [ ] Run `python run.py --map <map> --plan <plan>`
- [ ] Window opens; title is “PlanViz”
- [ ] Canvas shows obstacles + coordinates
- [ ] UI panel appears (embedded or separate “UI Panel” window)

### B. Navigation controls
- [ ] **Next** increases timestep by 1; agents animate smoothly
- [ ] **Prev** decreases timestep by 1; agents move back correctly
- [ ] **Play** runs continuously; disables Next/Prev/Go while running
- [ ] **Pause** stops running; controls re-enable
- [ ] **Restart/Reset** returns to start timestep; clears shown paths/arrows/tasks selection

### C. Zoom / pan
- [ ] Mouse wheel zooms in/out; text scales correctly
- [ ] Drag pans the canvas
- [ ] **Fullsize** resets zoom to initial scale

### D. Display toggles (both versions)
- [ ] **Show grids** toggles grid lines
- [ ] **Show agent indices** toggles agent id text
- [ ] **Show start locations** toggles grey start markers
- [ ] **Show colliding agents** colors conflict agents red (and restores when off)

### E. Conflicts / errors list
- [ ] Error list populates (header + entries)
- [ ] Selecting an error highlights involved agents red
- [ ] Double-click error jumps to that time (and highlights correctly)

### F. Event list
- [ ] Event list populates (header + entries)
- [ ] Double-click event jumps to the event time
- [ ] (2024) current timestep row highlights in yellow

### G. Tasks (2023)
- [ ] Task filter combobox changes which tasks are visible
- [ ] **Show task indices** toggles task id text (respecting task filter)
- [ ] Task colors update with time jump (**Go**)

### H. Overlays (2023, only if provided)
- [ ] Heatmap toggle shows/hides overlay cells
- [ ] Highway toggle shows/hides directional arrows
- [ ] Heuristic toggle shows/hides heuristic overlay
- [ ] Search tree combobox switches overlays and hides previous tree

### I. Agent path inspection
- [ ] (2023) Right-click agent toggles its path rectangles
- [ ] (2024) Left-click agent highlights next errand + draws arrows
- [ ] (2024) “Show selected agent path” enables/disables path display for selected agent

### J. Hover + popup (2024)
- [ ] Mouse position label updates while moving cursor
- [ ] Hover text appears only when checkbox enabled
- [ ] Right-click (or click occupied cell) opens popup window
- [ ] Popup lists show agent events / tasks at location
- [ ] Double-click popup entry jumps correctly

---

## 6) Mermaid flowchart (GUI flow)

```mermaid
flowchart TD
  A[Start: python run.py] --> B[Parse CLI args]
  B --> C[Read plan JSON -> detect version]
  C -->|2024 LoRR| D[PlanConfig2024: load map/paths/tasks/events/errors]
  C -->|2023 LoRR or default| E[PlanConfig2023: load map/paths/tasks/events/errors + optional overlays]
  D --> F[PlanViz2024: build UI panel + bind mouse events]
  E --> G[PlanViz2023: build UI panel + bind mouse events]
  F --> H[tk.mainloop()]
  G --> H

  subgraph User Interactions
    H --> I{User action}
    I -->|Play/Pause| J[Animate agents timestep-by-timestep]
    I -->|Next/Prev| K[Step timeline]
    I -->|Go| L[Jump to timestep -> update_curtime]
    I -->|Toggle checkboxes| M[Show/hide layers and labels]
    I -->|Conflict/Event list| N[Highlight/jump]
    I -->|Canvas click| O[Select agent / popup / path display]
    I -->|Wheel/Drag| P[Zoom/Pan]
    J --> I
    K --> I
    L --> I
    M --> I
    N --> I
    O --> I
    P --> I
  end
```
