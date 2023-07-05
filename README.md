# MAPF analysis
Python-based analitic tools for MAPF problems, which contains a visualizer and a data analyzer.
## One-shot Plan Visualizer
### Arguments
- `--map` (type: *str*): Path to the map file (ends with `.map`). See `example/maze-32-32-2.map` for more details.
- `--plan` (type: *str*): Path to the planned path file (ends with `.path`). See `example/result.path` for more details.
- `--n` (type: *int*): Number of agents need to show (*default*: All agents in the path file)
- `--grid` (type: *bool*): Whether to show the grids on the map (*default*: false)
- `--aid` (type: *bool*): Whether to show the agent indices (*default*: false)
- `--static` (type: *bool*): Whether to show the start and goal locations (*default*: false)
- `--ca` (type: *bool*): Whether to show the colliding agnets (*default*: false)
- `--ppm` (type: *int*):  Number of pixels per move, depending on the size of the map
- `--mv` (type: *int*):  Number of moves per timestep; the tile size of the map is `ppm` $\times$ `mv`.
- `--delay` (type: *float*):  Wait time for each timestep

If one is using [our maps](https://github.com/MAPF-Competition/benchmark_problems),
then we have default values for `ppm`, `mv`, and `delay`, so the user does not need to specify them.

One can also create a yaml file that includes all the arguments. See `example/config.yaml` for more details.
If so, then please use `--config` and specify the path to your yaml file.

### Run
To run the visualizer, open a terminal under directory `MAPF_analysis/visulaizer` and type the following command:
```bash
python plan_viz.py --map ./warehouse-small.map --plan ./warehouse-small-40.json 
```
