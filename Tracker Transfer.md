# Tracker Transfer
Tracker Transfer is a tool that helps to convert best-known solutions to a wide range of MAPF problems, as published by the community website [MAPF Tracker](http://tracker.pathfinding.ai/). Once converted, these plans can be visualised with PlanViz. 

To use this tool, you need a MAPF plan, and the corresponding scenario file (`.scen`) which contains the start and target locations of the agents. Both are available for download from the MAPF Tracker.

## Arguments
- `plan` (type: *str*): Path to the MAPF plan file (ends with `.csv`). See `example/random-32-32-20.csv` and `example/random-32-32-20_random_1_300.csv` for more information.
- `multiPlan`: Indicates whether the input plan file contains multiple MAPF plans (True if specified).
- `scen` (type: *str*): Path to scenario file for single plan file (ie. `example/random-32-32-20_random_1_300.csv`), path to the folder that contains the scenario files (ie. `example/scen-files`) if multiPlan is enabled.
- `outputFile` (type: *str*): Path to the output file without extension (ie. `example/transfer_result`).

## Run
The following example shows how to convert the plan (CSV format) for a single instance (300 agents on the map random-32-32-20, the corresponding scenario file is in `example/random-32-32-20-random-1.scen`). The result (JSON format) is placed in `../example/transfer_result`: 
```bash
python3 tracker_transfer.py --plan ../example/random-32-32-20_random_1_300.csv --scen ../example/random-32-32-20-random-1.scen --outputFile ../example/transfer_result
```

The following example shows how to convert [a set of plans](http://tracker.pathfinding.ai/results/) appearing in a single file (CSV format, on map random-32-32-20, the corresponding scenario files are in folder `example/scen-files`). The resulting files (JSON format) are all placed in `../example/transfer_result`:
```bash
python3 tracker_transfer.py --plan ../example/random-32-32-20.csv --scen ../example/scen-files --outputFile ../example/transfer_result --multiPlan
```

After converting a MAPF Tracker plan to the PlanViz format, you can then visualise the result. The following command refers to a MAPF plan (`example/mapf_plan_example.json`) that we converted earlier:
```bash
python3 plan_viz.py --map ../example/random-32-32-20.map --plan ../example/mapf_plan_example.json --grid --aid --static --ca
```
