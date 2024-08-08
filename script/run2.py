# -*- coding: UTF-8 -*-
""" Run the main function for PlanViz
"""

import argparse
import tkinter as tk
import numpy as np
from plan_config2 import PlanConfig2
from plan_viz2 import PlanViz2


def main() -> None:
    """ The main function of the visualizer.
    """
    parser = argparse.ArgumentParser(description="Plan visualizer for a MAPF instance")
    parser.add_argument("--map", type=str, help="Path to the map file")
    parser.add_argument("--plan", type=str, help="Path to the planned path file")
    parser.add_argument("--n", dest="team_size", type=int, default=np.inf,
                        help="Number of agents")
    parser.add_argument("--start", type=int, default=0, help="Starting timestep")
    parser.add_argument("--end", type=int, default=100, help="Ending timestep")
    parser.add_argument("--ppm", dest="ppm", type=int, help="Number of pixels per move")
    parser.add_argument("--mv", dest="moves", type=int, help="Number of moves per action")
    parser.add_argument("--delay", type=float, help="Wait time between timesteps")
    parser.add_argument("--grid", dest="show_grid", action="store_true",
                        help="Show grid on the environment or not")
    parser.add_argument("--aid", dest="show_ag_idx", action="store_true",
                        help="Show agent indices or not")
    parser.add_argument("--tid", dest="show_task_idx", action="store_true",
                        help="Show task indices or not")
    parser.add_argument("--static", dest="show_static", action="store_true",
                        help="Show start locations or not")
    parser.add_argument("--ca",  dest="show_conf_ag", action="store_true",
                        help="Show all colliding agents")
    parser.add_argument("--hm", dest="heat_maps", nargs="+", default=[],
                        help="Path files for generating heatmap")
    parser.add_argument("--hw", dest="hwy_file", type=str, default="",
                        help="Path files for generating highway")
    parser.add_argument("--searchTree", dest="search_tree_files", nargs="+", default=[],
                        help="Show the search trees")
    parser.add_argument("--heu", dest="heu_file", type=str, default="",
                        help="Show the low-level heuristics")
    args = parser.parse_args()

    plan_config = PlanConfig2(args.map, args.plan, args.team_size, args.start, args.end,
                              args.ppm, args.moves, args.delay)
    PlanViz2(plan_config, args.show_grid, args.show_ag_idx, args.show_task_idx,
             args.show_static, args.show_conf_ag)
    tk.mainloop()


if __name__ == "__main__":
    main()
