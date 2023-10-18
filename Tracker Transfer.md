# Tracker Transfer
Tracker Transfer is a tool that helps to convert best-known solutions to a wide range of MAPF problems, as published by the community website [MAPF Tracker](http://tracker.pathfinding.ai/). Once converted, these plans can be visualised with PlanViz. 

## Arguments
- `plan` (type: *str*): Path to the planned path file (ends with `.json`). See `example/random-32-32-20.csv` and `example/random-32-32-20_random_1_300.csv` for more information.
- `multiPlan`: Whether the plan path contains path for multiple instances or not. Set to True if specified.
- `scen` (type: *str*): Path to scenario file for single plan file (ie. `example/random-32-32-20_random_1_300.csv`), path to the folder that contains the scenario files (ie. `example/scen-files`) if multiPlan is enabled.
- `outputFile` (type: *str*): Path to the output file without extension (ie. `example/transfer_result`).

## Run
The following example shows how to convert the plan (CSV format) for a single instance (300 agents on the map random-32-32-20). The result (JSON format) is placed in `../example/transfer_result`: 
```bash
python3 tracker_transfer.py --plan ../example/random-32-32-20_random_1_300.csv --scen ../example/random-32-32-20-random-1.scen --outputFile ../example/transfer_result
```

The following example shows how to convert [a set of plans](http://tracker.pathfinding.ai/results/) appearing in a single file (CSV format) for (map random-32-32-20). The resulting files (JSON format) are all placed in `../example/transfer_result`:
```bash
python3 tracker_transfer.py --plan ../example/random-32-32-20.csv --scen ../example/scen-files --outputFile ../example/test/result --multiPlan
```

After converting a MAPF Tracker plan to the PlanViz format, you can then visualise the result as follows:
```bash
python3 plan_viz.py --map ../example/random-32-32-20.map --plan ../example/transfer_result.json --grid --aid --static --ca
```
