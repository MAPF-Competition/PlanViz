# Color palette and visual legend

PlanViz Qt uses a YAML file to configure agent, task, errand, and path colors.
Defaults come from the bundled `src/planviz_qt/palettes/Color_palette.yaml`;
color values are not duplicated in Python code.

## Changing colors

Copy the default YAML under a new name and edit the entries you need, or create
a smaller file containing only your overrides. For example, save this as
`my_palette.yaml` to change the normal agent color:

```yaml
version: 1
agent:
  idle: "#342353"
```

Omitted colors use the bundled defaults. The `version` field is optional in
custom files and defaults to version 1. Section and entry names are case
insensitive, so `Agent` and `Idle` also work. Saved copies use lowercase names.

Write colors as quoted six-digit hexadecimal values. `"#342353"` and
`'#342353'` are valid; an unquoted `#342353` is a YAML comment.
Color names such as `red`, three-digit values such as `#123`, and eight-digit
values containing alpha are unsupported.

The **Colors & legend** window provides these actions:

- **Load YAML**: load a custom file and merge it with the default palette.
- **Reload**: reread the active YAML file to apply edits. When using defaults,
  this rereads the bundled `Color_palette.yaml`.
- **Save copy**: save the complete merged palette to a new YAML file and make
  it the active file. Edit that file and choose **Reload** to apply changes.
- **Use defaults**: return to the bundled palette.

You can also select a palette at startup:

```bash
python run.py --palette /absolute/path/my_palette.yaml
```

Palettes are stored separately from plan JSON. To share the same colors, include
the YAML file and select it with `--palette` or **Load YAML**.

When running from source, you can edit the bundled YAML directly. A separate
custom file makes it easier to keep your settings across package updates.
Loading errors identify the file and invalid entry.

## Shapes and state colors

Shapes have fixed meanings. The palette configures their colors.

| Object | Shape | Palette section |
|---|---|---|
| Agent | Circle | `agent` |
| Intermediate errand in a task | Diamond | `errand` |
| Final destination of a task | Square | `task` |

When agent states overlap, the color priority is:

`collision > errand_completed > delayed > newly_assigned > idle`

`idle` means the normal state without a special recorded status; it also
includes moving agents. It does not classify an agent as stationary based on
its movement. `task.completed` and `errand.completed` indicate that completion
of the corresponding destination was recorded in the log.

When destinations share the exact same `(row, column)`, the display selects
the task with the greatest `release_time` among destinations allowed by the
current filters. Ties use the greatest `task_id`, then the greatest
`stop_index` for repeated visits by the same task. An asterisk (`*`) appears
only when at least two distinct displayed tasks overlap at that location.
Repeated visits by a single task do not add an asterisk.

## Available entries

| Section | Entries |
|---|---|
| `agent` | `idle`, `newly_assigned`, `delayed`, `errand_completed`, `collision`, `heading`, `index`, `selected_outline`, `collision_outline`, `start_fill`, `start_outline` |
| `task` | `unassigned`, `newly_assigned`, `assigned`, `completed`, `index` |
| `errand` | `unassigned`, `newly_assigned`, `assigned`, `completed`, `index` |
| `path` | `executed`, `remaining_errands` |

`index` controls the numeric label color. `heading` controls the agent heading
indicator; `selected_outline` and `collision_outline` control the corresponding
outlines. `start_fill` and `start_outline` control start location markers.
`path.executed` controls the selected path color. With **Show planned states**
enabled, the same color is used for the logged one-step predictions. The
`collision` fill applies when collision highlighting is enabled or an error
row is selected.

Selected paths run from the current time to the next unfinished errand, with
a limit of 2,000 consecutive states. `path.remaining_errands` colors the arrow
to that next errand. `agent.selected_outline` also colors the brief expanding
ring when an agent is newly selected; its persistent outline remains afterwards.

Start location fills use alpha `70/255`, and paths use alpha `170/255`.
Changing their RGB values in YAML preserves these alpha values. Map terrain,
grid lines, and analysis overlay color scales are outside this palette's scope.

## Validation and Python API

Unsupported versions, unknown sections or entries, duplicate keys (including
case variants), and invalid colors are rejected. Custom YAML tags, Python
object tags, and YAML merge keys (`<<`) are also rejected. Missing entries in
a custom palette are filled from the defaults.

The Python API does not import Qt:

```python
from planviz_qt.palette import load_palette, save_palette

palette = load_palette("my_palette.yaml")
color = palette.color("agent", "idle")  # "#342353"
full_schema = palette.as_dict()
save_palette(palette, "palette_copy.yaml")
defaults = load_palette()
```

`Palette` is immutable. `as_dict()` returns a separate dictionary, so editing
it does not change the active palette. A custom palette's `source` is its
absolute file path; the default palette's `source` is `None`. Read, validation,
and save errors are reported as `PaletteError`.
