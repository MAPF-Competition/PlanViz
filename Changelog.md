# Changelog


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