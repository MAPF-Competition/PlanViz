# PlanViz

Welcome to PlanViz! This is an **offline** (i.e., post-hoc) visualiser for analysing solutions to multi-robot and multi-agent coordination problems.
It is developed as a support tool for participants in the [League of Robot Runners](http://leagueofrobotrunners.org) competition.
However, PlanViz can also be used for a variety of similar problems which are outside the scope of the competition. 

PlanViz is implemented in python using the [`tkinter`](https://docs.python.org/3/library/tkinter.html), a Tcl/Tk GUI toolkit. An example of the application in action is shown in the following video.

![plan_viz_gif](images/plan_viz.gif)

## Installation

This project requires **Python 3.10 or higher**. Choose one of the following methods to install the required packages.

### Option1: Using [venv](https://docs.python.org/3/library/venv.html)
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/MAPF-Competition/PlanViz.git
    cd PlanViz
    ```
2.  **Verify your Python version:**

    Before creating the environment, check your default `python3` version. If the output version is less than 3.10, you'll need to use a specific Python command for a newer version you have installed (e.g., `python3.10`, `python3.11`).
    ```bash
    python3 --version
    ```

3.  **Create and activate a virtual environment:**
    * **macOS / Linux:**
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```
    * **Windows:**
        ```bash
        python -m venv venv
        .\venv\Scripts\activate
        ```

4.  **Install the required packages:**
    ```bash
    pip install -r requirements.txt
    ```

### Option 2: Using [Conda](https://docs.conda.io/en/latest/)
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/MAPF-Competition/PlanViz.git
    cd PlanViz
    ```

2.  **Create and activate a conda environment:**
    ```bash
    conda create --name planviz python=3.10
    conda activate planviz
    ```

3.  **Install the required packages:**
    ```bash
    pip install -r requirements.txt
    ```

## Run

Please refer to the [PlanViz instruction manual](./PlanViz.md) for details about how to use this tool and supported features. The following simple example shows how to visualise a plan file, from the JSON formatted descriptions produced by the Robot Runners start-kit.

Open a terminal and type the following command:

```bash
python3 script/run.py --map example/warehouse_small.map --plan example/warehouse_small_2024.json
```

## Tracker Transfer

Tracker Transfer is a tool that helps to convert best-known solutions to a wide range of MAPF problems, as published by the community website [MAPF Tracker](http://tracker.pathfinding.ai/). Once converted, these plans can be visualised with PlanViz. Please refer to the [Tracker Transfer instruction manual](./Tracker%20Transfer.md) for details about how to use this tool and supported features.
