# PlanViz JSON interchange, schema version 1

This is the common output contract of the input converters. For converter
implementation, registration, and testing, see [README.md](README.md).

## Document structure

The JSON document contains plan data. Its map is supplied separately; `map.width`
and `map.height` must match that map. Dimensions do not identify a particular map:
two maps with the same dimensions still require the user to choose the correct
one. Terrain is not duplicated in this document.

```json
{
  "format": "planviz",
  "schema_version": 1,
  "source_version": "2026 LoRR",
  "action_model": "MAPF_T",
  "time_unit": "tick",
  "ticks_per_step": 10,
  "max_time": 20,
  "map": {"width": 8, "height": 6},
  "agents": [
    {"start": [2, 2, 0], "actual": [["F", 10], ["W", 10]]}
  ],
  "tasks": [
    {
      "id": 5,
      "release_time": 0,
      "stops": [[2, 3]],
      "assignments": [[0, 0]],
      "completions": [[10, 0, 0]]
    }
  ],
  "events": [
    {"time": 0, "agent_id": 0, "task_id": 5,
     "kind": "assigned", "stop_index": null, "id": "assigned:0:0:5:None:0"},
    {"time": 10, "agent_id": 0, "task_id": 5,
     "kind": "task_finished", "stop_index": 0, "id": "task_finished:10:0:5:0:0"}
  ],
  "conflicts": [],
  "delays": {},
  "metadata": {"solver": "example"}
}
```

### Header and coordinates

| Field | Meaning |
|---|---|
| `format` | Required literal `"planviz"`; used for format detection. |
| `schema_version` | Required integer `1`. Other versions are rejected rather than guessed. |
| `source_version` | Original input label, such as `"2023 LoRR"`. Optional; defaults to `"PlanViz v1"`. It is provenance, not a parser selection. |
| `action_model` | Required `"MAPF"` or `"MAPF_T"`. |
| `time_unit` | Required `"tick"` or `"timestep"`. |
| `ticks_per_step` | Required positive integer; logical units per cell move or quarter turn. Must equal `1` with `"timestep"`. |
| `max_time` | Required nonnegative integer, at least the length of every actual and planned sequence. |
| `map` | Required object with positive integer `width` and `height`. |
| `agents` | Required array. The array index is the zero-based agent ID. An empty team is valid. |

Coordinates are `[row, column]`. Agent starts use `[row, column, direction]`.
Coordinates and directions must be finite numbers. Direction is measured in
quarter turns: `0 = east`, `1 = north`, `2 = west`, `3 = south`; fractional
directions in `[0, 4)` are valid. MAPF also permits `-1` for an unspecified
heading. The JSON format uses numeric headings rather than strings such as `E`.

All times, task IDs, agent IDs and stop indexes are integers; booleans and decimal
numbers are rejected for those fields. Times are nonnegative. Release times,
events and delay endpoints may extend beyond `max_time` so truncated execution
logs can retain their diagnostics. Playback still ends at `max_time`.

### Compressed actual and planned motion

Each agent requires `start` and `actual`. A motion sequence is an array of
`[action, duration]` runs. Each duration is a strictly positive integer in the
document's time unit. `[]` is a valid empty sequence and leaves the agent at its
start. Adjacent identical actions are merged on import. A billion-tick wait is
represented as `[["W", 1000000000]]`, without a billion positions or actions.

| Model | Actions and coordinate effects per `ticks_per_step` units |
|---|---|
| `MAPF_T` | `F`: forward in the current direction; `R`: clockwise quarter turn; `C`: counterclockwise quarter turn; `W`: wait. |
| `MAPF` | `R`: column +1; `L`: column −1; `U`: row +1; `D`: row −1; `W`: wait. Heading is unchanged. |

The MAPF `U`/`D` convention above intentionally preserves the existing LoRR
decoder. A converter from another coordinate convention must translate its
actions or coordinates before constructing the common model.

Actual runs accumulate from the agent's start. Tick inputs interpolate a forward
move or rotation analytically according to `ticks_per_step`. No motion history
is expanded into a dense agent-by-time array.

An optional `planned` sequence has a specific meaning: **one-unit predictions
from the preceding actual state**, matching the LoRR planner log. At integer
time `t > 0`, the planned state is the actual state at `t - 1` advanced by the
planned action for that interval. Planned actions do not accumulate into an
independent simulated trajectory. At `t = 0`, planned and actual both use the
start. After a planned sequence ends, its final predicted state is held. Actual
sequences similarly hold their final actual state after ending.

When `planned` is absent, it uses the actual action sequence. Export omits
`planned` when its runs are equal to `actual`, avoiding redundant histories. An
explicit empty `planned: []` is distinct from omission: it holds the start even
when the actual path moves.

### Tasks, events, conflicts and delays

These fields are optional and default to empty arrays or objects. Records use
the field names of the shared domain model.

| Field | Record shape and meaning |
|---|---|
| `tasks` | `{id, release_time, stops, assignments, completions}`. `stops` is an ordered array of `[row, column]`. `assignments` contains `[time, agent_id]`; `completions` contains `[time, agent_id, stop_index]`. Both histories default to empty. |
| `events` | `{time, agent_id, task_id, kind, stop_index, id}`. `stop_index` is optional or `null`. `id` is optional and defaults to an empty string; source IDs are preserved. Existing event kinds are `assigned`, `errand_finished`, and `task_finished`; other nonempty strings are retained as diagnostic labels. |
| `conflicts` | `{time, agent_ids, description, task_id}`. `agent_ids` is an array of unique IDs and may be empty for general errors such as planner timeouts. `task_id` is optional or `null`. |
| `delays` | An object keyed by decimal agent ID strings, for example `{"0": [[2, 5], [10, 12]]}`. Each interval is inclusive and must satisfy `0 <= start <= end`. |
| `metadata` | Arbitrary JSON object for source information, summary statistics and warnings. Tuples in the Python model export as JSON arrays. Non-finite numbers and non-JSON values are rejected. |

Task IDs must be unique. References to agents and known task stops are checked.
Events and conflicts may reference an unavailable task ID because existing LoRR
logs use these records to diagnose missing or invalid tasks. Those records and
their source warnings are retained. Import does not invent missing tasks.

Task assignment/completion histories determine the task's displayed state;
events determine the event list and productivity statistics. Both are stored
explicitly and preserved independently. A new converter should populate them
consistently. Import sorts task histories, events and conflicts by time, retaining
their input order for ties; it does not infer task histories from the event list.

Loading a smaller `team_size` keeps the prefix of the agent array. Associated
events, assignments, completions and delays are filtered to that prefix; task
locations and conflict diagnostics are retained. The complete input is validated
before filtering, so a malformed excluded agent cannot silently pass validation.

### Python API and validation boundary

```python
from planviz_qt.converters.exchange import decode_document, dump_plan, plan_to_document

document = plan_to_document(plan)           # PlanData -> JSON-compatible dict
output_path = dump_plan(plan, "plan.json") # UTF-8 JSON; compressed runs retained
restored = decode_document(document, map_data)
```

The decoder also accepts `team_size`, `progress(percent, message)` and a
`cancelled()` callback. Syntax and contract errors raise `ValueError`;
cancellation raises `InterruptedError`. The application loader wraps these in
its standard input errors.

Validation checks the interchange contract, dimensions, supported models,
numeric types, references and motion runs. It does not prove a solver's path is
collision-free, inside the map, or kinematically valid. Erroneous paths remain
available for inspection. Future schema versions require an explicit decoder
update. Unknown extra fields in a version-1 document are ignored; store data
that must survive a round trip inside `metadata`.

The implementation reconstructs exported runs from compressed table boundaries
through `PathStore.iter_motion_sequences()`. It does not keep a second complete
source history or sample positions for serialization.
