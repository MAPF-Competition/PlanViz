# PySide6 migration

The `qt-migration` branch makes the Qt implementation the primary application.
The existing Qt implementation was committed before reorganizing the repository,
so its pre-move state remains available in Git history.

## Repository layout

- `run.py`: launch directly from a source checkout.
- `pyproject.toml` and `requirements.txt`: package configuration and Qt dependencies.
- `src/planviz_qt/`: application, input converters and bundled palette.
- `tests/`: domain, converter, rendering and application checks.
- `docs/`: screenshots, their capture tool and migration notes.
- `benchmarks/`: recorded measurements and the replay benchmark tool.
- `example/`: shared maps, solution logs and converter input examples.

The Python import name remains `planviz_qt`; installed commands remain
`planviz-qt` and `planviz-convert`. The input formats and playback behavior are
unchanged by the directory move.

## Updated commands

Run these commands from the repository root in an activated Python environment.

| Previous command | Current command |
| --- | --- |
| `python -m pip install -r qt/requirements.txt` | `python -m pip install -r requirements.txt` |
| `python qt/run.py` | `python run.py` |
| `python -m pip install -e ./qt` | `python -m pip install -e .` |
| `PYTHONPATH=qt/src python -m planviz_qt.converters --help` | `PYTHONPATH=src python -m planviz_qt.converters --help` |
| `python qt/docs/capture_screenshots.py` | `python docs/capture_screenshots.py` |

Update IDE launch configurations and scripts that refer to `qt/run.py`,
`qt/src`, or `script/run.py`. Existing input paths under `example/` still work.

```sh
python -m pip install -r requirements.txt
python run.py --map example/warehouse_small.map --plan example/warehouse_small_2026.json
```

See the [user guide](../README.md) for controls, examples and the full CLI.

## Original Tkinter release

The Tkinter application, original requirements and old manuals are preserved in
the `v3.2.0` Git tag. To inspect or run them without replacing the Qt checkout:

```sh
git worktree add --detach ../PlanViz-tkinter v3.2.0
```

Follow that checkout's README and use a separate virtual environment for its
dependencies. The Qt branch retains the project's license and historical
changelog, while its active user guide and entry point describe the Qt app.

Local virtual environments, IDE files and unrelated personal working files are
not part of the migration commits.
