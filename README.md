# PlanViz

Welcome to PlanViz! This is an **offline** (i.e., post-hoc) visualiser for analysing solutions to multi-robot and multi-agent coordination problems.
It is developed as a support tool for participants in the [League of Robot Runners](http://leagueofrobotrunners.org) competition.
However, PlanViz can also be used for a variety of similar problems which are outside the scope of the competition. 

PlanViz is implemented in python using the [`tkinter`](https://docs.python.org/3/library/tkinter.html), a Tcl/Tk GUI toolkit. An example of the application in action is shown in the following video.

![plan_viz_gif](images/plan_viz.gif)

## Run

Please refer to the [PlanViz instruction manual](./PlanViz.md) for details about how to use this tool and supported features. The following simple example shows how to visualise a plan file, from the JSON formatted descriptions produced by the Robot Runners start-kit.

Open a terminal and type the following command:

```bash
python3 script/run.py --map example/warehouse_small.map --plan example/warehouse_small_2024.json --grid --aid --tid
```

## Tracker Transfer

Tracker Transfer is a tool that helps to convert best-known solutions to a wide range of MAPF problems, as published by the community website [MAPF Tracker](http://tracker.pathfinding.ai/). Once converted, these plans can be visualised with PlanViz. Please refer to the [Tracker Transfer instruction manual](./Tracker%20Transfer.md) for details about how to use this tool and supported features.
