# Writing PlanViz converters

Each input format has a converter that translates source data into the shared `PlanData` model. Rendering and playback do not interpret source JSON fields or LoRR versions. To support a new format, add a converter in this folder and register it.

```text
Source JSON + existing map reader
        ↓
io.loader.load_plan()
        ↓  Auto-detection or --format selection
ConverterRegistry → selected converter.convert()
        ↓
PlanData → Qt rendering / playback / analysis
        ↓ dump_plan()
Normalized PlanViz JSON → reload later
```

The default converters are `lorr-2023`, `lorr-2024`, `lorr-2026`, and `planviz`. All three LoRR converters support both `MAPF` and `MAPF_T`. This organization does not add new MovingAI result formats.

## File guide

| File | Responsibility |
| --- | --- |
| `base.py` | `InputConverter` and `ConversionContext` contracts |
| `registry.py` | Registration, automatic detection, and explicit selection |
| `lorr.py` | Interpretation of LoRR 2023/2024/2026 source fields |
| `motions.py` | Conversion of LoRR action strings and segmented RLE into compressed motion runs |
| `exchange.py` | Normalized JSON serialization, validation, and decoding; `PlanVizConverter` |
| `legacy.py` | Existing tracker CSV and coordinate-path text conversion helpers |
| `cli.py`, `__main__.py` | The `normalize`, `tracker`, and `paths` commands |
| `errors.py` | Conversion and loading exceptions |
| `example.py` | A small converter example to copy and adapt |
| `__init__.py` | Public API for external callers |

File reading and converter dispatch remain in `io/loader.py`. Converter modules at the old `io` paths are compatibility forwarders. Use `planviz_qt.converters` for new implementations and imports.

## 1. Define the source semantics

Establish the following conventions before writing a converter to avoid replaying the same path in the wrong direction or at the wrong speed.

- Coordinate order: `(row, column)` or `(x, y)`, including the origin and direction of each axis.
- Movement model: `MAPF`, or `MAPF_T` with headings and rotation actions.
- Time: consecutive timesteps indexed by array position, explicit timestamps, or tick durations.
- Initial state: included as the first path element or supplied separately.
- Planner history: an independent complete trajectory or one-step predictions based on the preceding executed state.
- Tasks, completions, errors, and delays: recorded observations or values inferred from path endpoints.

The shared model uses `(row, column, direction)` states, with `E=0`, `N=1`, `W=2`, and `S=3`. `MAPF` can represent an absent heading as `-1`.

**Action letters can have different meanings in different source formats.** The shared path store follows the existing LoRR MAPF convention: `U` increases the row, `D` decreases the row, `R` increases the column, and `L` decreases the column. If an external format uses `U` for upward movement, its converter must map that action to `D`. For MAPF_T, `F` moves forward, `R` rotates clockwise, and `C` rotates counterclockwise. `W` and `T` leave position and heading unchanged.

For `time_unit="timestep"`, use `ticks_per_step=1`. For tick inputs, `ticks_per_step` is the number of ticks required to move one cell or rotate 90 degrees. It is independent of playback speed and rendering FPS.

## 2. Implement the converter contract

`InputConverter` is a Protocol. Implement the following attributes and methods; explicit inheritance is unnecessary.

```python
class MyConverter:
    id = "my-format"          # Unique ID used by the CLI and Open dialog
    label = "My planner JSON"

    def can_read(self, data: dict) -> bool:
        return data.get("format") == self.id

    def convert(self, data: dict, context: ConversionContext) -> PlanData:
        ...
```

`can_read()` should perform a lightweight structural check without modifying the input. Prefer a `format` field or an unambiguous version tag. If multiple converters return true, automatic detection raises an error and requires an explicit `--format` selection.

**Validate the input in `convert()` as well.** Explicit `--format` selection calls the converter without consulting `can_read()`. Report malformed fields, mismatched agent counts, unsupported actions, and unsupported time representations with a clear `ValueError`. The loader wraps it in a `PlanLoadError` that includes the source filename.

| `ConversionContext` field | Usage |
| --- | --- |
| `map_data` | The already loaded map, exposing `width`, `height`, and `grid` |
| `source` | The source JSON file's `Path` |
| `team_size` | Number of agents to retain from the beginning; `None` retains all agents |
| `progress` | Callback receiving `(integer percentage, message)`, or `None` |
| `cancelled` | Function returning whether cancellation was requested, or `None` |
| `checkpoint(percent, message)` | Checks cancellation and reports progress together |

Call `checkpoint()` in long-running loops and keep progress monotonic. Do not catch and ignore `LoadCancelled` or `InterruptedError`. The loader's single `json.load()` call cannot be interrupted, but subsequent conversion and path indexing check for cancellation.

## 3. Working example

The `ExampleConverter` in [example.py](example.py) reads this small source format:

```json
{
  "format": "example-actions",
  "action_model": "MAPF_T",
  "starts": [[1, 1, 0]],
  "actions": ["F,R,F"],
  "metadata": {"solver": "my-planner"}
}
```

Agent IDs are array indices. `starts` contains numeric states at t=0, and each action in `actions[0]` consumes one timestep. The example produces these states:

| Time | Row | Column | Heading |
| --- | --- | --- | --- |
| 0 | 1 | 1 | E (0) |
| 1 | 1 | 2 | E (0) |
| 2 | 1 | 2 | S (3) |
| 3 | 2 | 2 | S (3) |

The example implements these rules:

- `starts` and `actions` must contain the same number of agents. Empty agent lists and empty action strings are allowed.
- `action_model` is required, and each movement model has its own allowed action set.
- `motions.py` compresses actions into runs. The converter then builds a normalized document and passes it to `decode_document()`.
- The shared decoder validates numbers, headings, runs, and agent filtering, then constructs `PathStore`. It validates excluded agents too and preserves the complete time range.
- Metadata is preserved, with the actual input path recorded in `metadata.source`. The source object is not modified.
- Tasks, completion events, and conflicts are not invented when absent from the source.
- Unknown top-level fields are rejected. Adding fields such as `plannerPaths`, `goals`, or `time_unit` requires an explicit extension of the converter contract.
- This example uses fixed timesteps. It rejects segmented RLE strings so tick durations cannot silently be interpreted as timesteps.

Normalized JSON validation does not determine whether a planner solution is collision-free. This tool displays execution results for inspection; do not claim collision validation or solution validity that the converter does not establish.

The loader also runs common task-record diagnostics after conversion. Timing
inconsistencies become aggregated warnings without changing the records; malformed
structure stops loading. See the [input validation policy](../../../VALIDATION_POLICY.md)
for the precise boundary and guidance on converter-specific checks.

## 4. Try a converter without changing the defaults

`ExampleConverter` is **not registered by default**. The following example creates a registry for the current process and saves the converted plan as normalized JSON. Run these commands from the repository root.

```sh
PYTHONPATH=qt/src .venv/bin/python - <<'PY'
import json
from pathlib import Path
from tempfile import gettempdir

from planviz_qt.converters import default_registry, dump_plan
from planviz_qt.converters.example import ExampleConverter
from planviz_qt.io.loader import load_plan

folder = Path(gettempdir()) / "planviz-converter-guide"
folder.mkdir(exist_ok=True)
map_path = folder / "small.map"
source_path = folder / "example.json"
output_path = folder / "normalized.json"
map_path.write_text(
    "type octile\nheight 4\nwidth 4\nmap\n....\n....\n....\n....\n",
    encoding="utf-8",
)
source_path.write_text(json.dumps({
    "format": "example-actions",
    "action_model": "MAPF_T",
    "starts": [[1, 1, 0]],
    "actions": ["F,R,F"],
}), encoding="utf-8")

registry = default_registry()
registry.register(ExampleConverter())
plan = load_plan(map_path, source_path, registry=registry)  # Auto-detect
# Add input_format="example-actions" to select the converter explicitly.
assert plan.paths.positions(3).tolist() == [[2.0, 2.0, 3.0]]
dump_plan(plan, output_path)
print(f".venv/bin/python qt/run.py --map {map_path} --plan {output_path} --format planviz")
PY
```

Use the printed command to open the normalized JSON in the viewer. The built-in `planviz` converter reads that file even though the example converter is not registered in the default application. With the package installed, the same Python API works without `PYTHONPATH=qt/src`.

## 5. Add a format to the CLI and Open dialog

To make a format available in the default application, add its converter to `default_registry()` in [registry.py](registry.py). For example, registering the example as a default format would look like this:

```python
from .example import ExampleConverter

def default_registry() -> ConverterRegistry:
    return ConverterRegistry((
        LoRR2023Converter(),
        LoRR2024Converter(),
        LoRR2026Converter(),
        PlanVizConverter(),
        ExampleConverter(),
    ))
```

`available_formats()` uses this registry. After restarting the application, the format appears in the `--format` choices, `--list-formats`, the Open dialog's Format list, and `normalize --format`. No format-specific branches are needed in `MainWindow`, playback, or individual CLI commands. Registering a converter only in the local `registry` variable from the previous section does not change the defaults in another process.

```sh
.venv/bin/python qt/run.py --list-formats
PYTHONPATH=qt/src .venv/bin/python -m planviz_qt.converters --help
PYTHONPATH=qt/src .venv/bin/python -m planviz_qt.converters normalize \
  --map example/warehouse_small.map \
  --plan example/warehouse_small_2026.json \
  --format lorr-2026 --output /tmp/planviz-normalized.json
.venv/bin/python qt/run.py --inspect \
  --map example/warehouse_small.map \
  --plan /tmp/planviz-normalized.json --format planviz
```

The installed command is `planviz-convert`, which runs the same CLI as `python -m planviz_qt.converters`. `--version` remains available for compatibility with existing LoRR calls; use `--format` for new formats.

## 6. More complex inputs and the exchange format

See [FORMAT.md](FORMAT.md) for the required normalized JSON fields and detailed schema rules.

For complex timing, task, or error structures, a converter can construct `PlanData`, `Task`, `Event`, `Conflict`, `MotionSequence`, and `PathStore` directly, as `lorr.py` does. For simpler adapters, reuse the shared validation in `decode_document()`, as demonstrated by the example.

`planned` represents a one-step prediction obtained by applying the planner action to the preceding **actual executed state**. Placing an independently integrated alternative trajectory in this field changes its meaning. If the source uses different semantics, define the supported interpretation explicitly before converting it. `plan_to_document()` and `dump_plan()` retain execution and planner runs without expanding them into a state for every tick.

Normalized JSON records map dimensions; the terrain map file is loaded separately. Distribute the original map together with the normalized JSON.

The default `load_plan()` reads JSON files. Adding a CSV or binary parser to `can_read()` does not make the loader read those file types automatically. Use a separate reader to load the source and call `convert(data, context)`, or generate normalized JSON for the application. The existing `convert_tracker()` and `convert_paths()` helpers in `legacy.py` read their established source formats and produce LoRR 2023 JSON. They remain available through the CLI in this folder.

## 7. Validation checklist

- Automatic detection and explicit format selection produce equivalent results.
- Each claimed movement model has correct axis directions and 90-degree rotations.
- Timestep and tick boundaries, empty paths, and agents with different path lengths are handled correctly.
- Execution and planner prediction semantics are preserved even when their actions differ.
- Source tasks, events, errors, and delays survive conversion without invented completion records.
- Agent limits preserve valid record references and the intended time range.
- Unsupported fields and time representations are rejected instead of silently ignored.
- Saving and reloading preserve states and records, without expanding long runs in proportion to their tick count.
- Conversion handles cancellation and does not import Qt.

Run the example tests and existing contract tests with:

```sh
PYTHONPATH=qt/src .venv/bin/python -B -m unittest discover \
  -s qt/tests -p 'test_converter_example.py' -v
PYTHONPATH=qt/src .venv/bin/python -B -m unittest discover \
  -s qt/tests -p 'test_input_formats.py' -v
PYTHONPATH=qt/src .venv/bin/python -B -m unittest discover \
  -s qt/tests -p 'test_exchange.py' -v
```
