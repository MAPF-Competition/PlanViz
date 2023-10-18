# Tracker Transfer
PlanViz also support visualising a MAPF plan. To do this, you need to provide the same JSON output format as the [robot runner startkit output](https://github.com/MAPF-Competition/Start-Kit/blob/main/Input_Output_Format.md). You can transfer your MAPF plan to the required format, in which set the `actionModel` property to `MAPF`, and run PlanViz.

We also provide transfer tools that can help you to transfer the MAPF plan from [MAPF tracker](http://tracker.pathfinding.ai/) to the required JSON output format. 

## Arguments
- `plan` (type: *str*): Path to the planned path file (ends with `.json`). See `example/random-32-32-20.csv` and `example/random-32-32-20_random_1_300.csv` for more information.
- `multiPlan`: Weather the plan path contains path for multiple instances or not. Set to True if specified.
- `scen` (type: *str*): Path to scenario file for single plan file (ie. `example/random-32-32-20_random_1_300.csv`), path to the folder that contains the scenario files (ie. `example/random-32-32-20.csv`) if multiPlan is enabled.
- `outputFile` (type: *str*): Path to the output file without extension (ie. `example/transfer_result`).

## Run Tracker Transfer
To run Tracker Transfer to view MAPF plan, open a terminal under the directory `PlanViz/script` and type the following example command:

If you are running tracker_transfer.py for plan of multiple instances
```bash
python3 tracker_transfer.py --plan ../example/random-32-32-20.csv --scen ../example/scen-files --outputFile ../example/test/result --multiPlan
```

If you are running tracker_transfer.py for plan of single instance 
```bash
python3 tracker_transfer.py --plan ../example/random-32-32-20_random_1_300.csv --scen ../example/random-32-32-20-random-1.scen --outputFile ../example/transfer_result
```

After you transfer the mapf tracker plan to the PlanViz support json format, you can then visualise the plan by running the PlanViz
```bash
python3 plan_viz.py --map ../example/random-32-32-20.map --plan ../example/transfer_result.json --grid --aid --static --ca
```
