# Changelog

## Unreleased — PySide6 migration

- Promote the PySide6 application from `qt/` to the repository root. Run it with
  `python run.py`, or install this directory and use `planviz-qt`.
- Replace the Tkinter application, dependencies and manuals on this branch with
  the Qt implementation and its illustrated user guide. The original release
  remains available under the `v3.2.0` tag.
- Include LoRR 2023/2024/2026 and MAPF/MAPF_T input adapters, a common JSON format,
  converter tools, compressed replay, agent/task inspection, visual settings,
  configurable palettes, solution details, productivity charts and overlays.
- Keep shared example data and update tests, documentation captures and
  benchmark tools for the root layout.

Version 3.2.0 - 2026-06-02
---
Added:
- Added LoRR 2026 example maps and output files under `example/LoRR2026`.
- Added solution metadata popup next to the time label, showing agent count, map size, traversable cells, obstacle cells, and agentMaxCounter.
- Added `Productivity` popup for task and errand timelines, with completed, instant, and throughput views.

Bug Fixes:
- Fixed zoom drift by preserving the cursor-focused viewport during wheel zoom.
- Fixed large-map viewport resizing so the minimap and visible region stay synchronized after canvas resize.
- Fixed `Fullsize` behavior to fit the whole map into the visible canvas instead of only resetting to the default zoom.

Changes:
- Updated the time label to show `Tick` for tick-based 2026 plans and include the maximum timestep.
- Updated event counters to show current and total counts where full totals are available.

Version 3.1.0 - 2026-04-09
---
Added:
- Added minimap for large map navigation with viewport mode, enabling click-and-drag panning.
- Added delay visualization feature for large maps.
- Added event frequency counter in the control panel showing cumulative counts for assigned, errand finished, and task finished events.
- Added double-click on event/error entries to center the viewport on the corresponding agent.
- Added collision highlighting: "Show colliding agents" toggle displays a red outline on agents that collided at any point, and fully red fill on agents colliding at the current timestep.
- Added color legend with markers matching the actual agent rendering styles.

Bug Fixes:
- Fix event navigation flicker when selecting agents.

Changes:
- Set default event limit to 100 and max visible errors/events to 15.
- Updated example command and documentation to use 2026 examples.

# Changelog
Version 3.0.0 - 2026-03-12
---
Added:
- Added support for `2026 LoRR` plan files, including tick-based timelines, segmented RLE path decoding, `makespanTicks`, `agentMaxCounter`, and schedule error loading.
- Unified the 2024/2026 UI and documentation around `Time` instead of `Timestep`, including start/end controls and playback labels.
- Added `--window` support to load and extend path data incrementally, reducing upfront rendering cost for long runs.
- Added `--event-limit` and dynamic event panel sizing so recent events remain readable on dense simulations.
- Improved rendering performance:
  - [numba](http://numba.pydata.org)-accelerated path computation
  - Lazy task rendering
  - Incremental agent path rendering

Changes:
- Fix a few rendering bugs in 2.1.0.

# Changelog
Version 2.1.0 - 2023-11-17
---
Added:
- Event list is refactored to better support the visualization of the task schedule.
- Events are sorted by the timestep, and new events are shown on the top by the progress of the visualisation.
- Right click a location show agents with tasks including the location.
- Auto-adjust the grid size to fit the window size for unknown maps.

Changes:
- Merge `run.py` and `run2.py` into `run.py`. PlanViz now checks the version of the JSON file and parses it accordingly.
- Fix a few rendering bugs in 2.0.0.

Version 2.0.0 - 2023-10-10
---
Added:
- `run2.py` for parsing and visualising JSON output from LORR Start-kit V2.0.0
- Task schedule visualisation: scheduler error and errands visualisation.
- Right click on agents to show current paths and scheduled tasks for the selected agents.
- Right click on empty tiles to cancel all selections.

Changes:
- `run.py` for parsing and visualising JSON output from LORR Start-kit V1.

Version 1.3.0 - 2023-10-21
---
Added:
- Show not only the path but tasks when right-click an agent.
- Transform plans from one-shot MAPF tracker to JSON file (see `tracker_transfer.py`).
- Support one-shot MAPF problem visualization.
- Show one previous task before start timestep.

Changed:
- Minimum requirements of JSON file are "actionModel", "AllValid", "teamSize", and "start"


Version 1.2.0 - 2023-08-27
---
Added:
- Plan configurations that contain
    - The map and the plan from the user-specified files.
    - The loading and rendering methods for visualization.

Changed:
- Separate the plan configurations and the control panel (which is PlanViz itself)
- Distribute input arguments to plan configurations and control panel
- Refactorize the code for a better understanding


Version 1.1.1 - 2023-08-24
---
Fix bugs:
- Fix bugs for direction settings
- Change task colors according to the timestep


Version 1.1.0 - 2023-08-19
---
Added:
- Add Changelog.md for tracking version changes

Changed:
- Use events to control tasks
- Setup start timestep and end timestep
- Generate a new UI window for large maps


Version 1.0.0 - 2023-07-12
---
Initial release of the project
