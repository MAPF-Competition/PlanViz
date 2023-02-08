# MAPF analysis
Python-based analitic tools for MAPF problems, which contains a visualizer and a data analyzer.
## Plan Visualizer
### Arguments
- `--map` (type: *str*): Path to the map file (ends with `.map`). See `example/maze-32-32-2.map` for more details.
- `--scen` (type: *str*): Path to the scen file (ends with `.scen`). See `example/maze-32-32-2-random-2.scen` for more details.
- `--path` (type: *str*): Path to the path file (ends with `.path`). See `example/result.path` for more details.
- `--n` (type: *int*): Number of agents need to show (*default*: All agents in the path file)
- `--grid` (type: *bool*): Whether to show the grids on the map (*default*: false)
- `--aid` (type: *bool*): Whether to show the agent indices (*default*: false)
- `--static` (type: *bool*): Whether to show the start and goal locations (*default*: false)
- `--ca` (type: *bool*): Whether to show the colliding agnets (*default*: false)
- `--ppm` (type: *int*):  Number of pixels per move, depending on the size of the map
- `--mv` (type: *int*):  Number of moves per timestep; the tile size of the map is the multiplication of `ppm` and `mv`.
- `--delay` (type: *float*):  Wait time for each timestep

If one is using the map from the [mapf benchmarks](https://movingai.com/benchmarks/mapf.html),
then we have default values for `ppm`, `mv`, and `delay`, so the user does not need to specify them.

One can also create a yaml file that includes all the arguments. See `example/config.yaml` for more details.
If so, then please use `--config` and specify the path to your yaml file.

### Run
To run the visualizer, open a terminal under directory `MAPF_analysis/visulaizer` and type one of the following commands:
```bash
python plan_vis.py --map ./example/maze-32-32-2.map --scen ./example/maze-32-32-2-random-2.scen --path ./example/result.path 

python plan_vis.py --config ./example/config.yaml
```
