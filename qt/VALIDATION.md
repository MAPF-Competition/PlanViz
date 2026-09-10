# Migration validation — 2026-09-08

All implementation changes are contained in `qt/`. The original `script/`,
requirements, documentation, examples and existing local work were preserved.
No Tkinter imports or dependencies on the original application's modules occur
in the new production package.

**Environment:** macOS, Python 3.12.13, PySide6/Qt 6.11.1, NumPy 2.2.6,
Matplotlib 3.10.6. GUI tests use `QT_QPA_PLATFORM=offscreen`; no visible desktop
window was opened as part of the automated migration.

**Initial migration tests:** 69 tests passed in the combined run (4.777 seconds).

| Area | Tests |
| --- | ---: |
| Compressed paths, input versions, events and delays | 16 |
| Analytics and task state | 11 |
| Tracker and coordinate-path converters | 8 |
| Analysis overlay readers | 10 |
| Graphics, camera, minimap and rendering | 13 |
| Playback, main-window integration and worker lifecycle | 11 |

The suite loads all 12 repository JSON fixtures at full agent counts. It covers
empty/short paths, fractional motion, a billion-tick compressed path, bounded
snapshot caches, executed-vs-planned semantics, reassignment, reverse seeks,
stable event IDs, same-time conflicts, overlapping delays, service-action traffic
occupancy, combined heatmaps, cancellation and stale-worker result rejection.

The scene tests verify that a large map with 10,000 agents still has only two
base scene items. They check cursor-anchor invariance, finite hit testing,
independent ID toggles, coincident-agent fills, task cache invalidation, heuristic
zero cells, live task-sequence anchors and actual warehouse/iron rendering.

**Original motion comparison:** selected initial, boundary and late states from
the first/middle/last agents in all 12 fixtures were compared against the original
decoders and Numba movement kernels. All 798 actual/planned sample-state
comparisons matched after six-decimal rounding. This is sampled numerical
equivalence, not exhaustive equivalence of every state and every original UI
operation.

**Task optimization comparison:** all 40 before/after marker snapshots for the
iron 10,000-agent fixture matched exactly. These cover assigned/next modes,
all-agent/selected-agent views and ten times through the recording.

**Large-input smoke:** `--inspect` loaded the iron plan with 10,000 agents on the
1800 × 1912 map, and returned finite initial/middle/final states. The compressed
path arrays plus those snapshot-cache entries used 12,781,654 bytes. This excludes
the rest of the application's memory. A local loading/indexing/inspection sample
took approximately 0.70 seconds; it is not a repeatable hardware benchmark.

A separate serial offscreen main-window sample requested ticks 10 through 29
with the Assigned task layer enabled. It displayed 19,832 task markers and
10,000 agents, retaining two scene items. Median snapshot-update callback time
was 12.831 ms; p95 was 20.758 ms across 20 calls. This excludes paint/presentation
latency and therefore must not be interpreted as achieved desktop FPS.

Small warehouse, large iron and Productivity screenshots were rendered and
visually inspected. Native window management, high-DPI appearance and touchpad
behavior still need interactive checks on the target desktop before a release.

**Packaging:** a Python wheel built successfully. It was installed without
dependencies into a temporary isolated target. From outside the repository, its
`python -m planviz_qt --inspect` command successfully loaded a supplied fixture,
and the installed `planviz-convert` entry point ran. The legacy virtual
environment was not changed; build-only dependencies were placed under `/tmp`.

Reproduce the tests from the repository root:

```sh
QT_QPA_PLATFORM=offscreen MPLCONFIGDIR=/tmp/planviz-qt-mpl \
  PYTHONPATH=qt/src .venv/bin/python -B -m unittest discover -s qt/tests -v
```

**Intentional behavioral changes:** malformed actions produce explicit load
errors; overlapping delays are merged; all same-time conflict agents are indexed;
the coordinate-path converter fixes the old vertical-action inversion. Missing
task references in older incomplete logs remain inspectable with metadata
warnings. New world-coordinate rendering replaces legacy pixel/move controls,
and selected trajectories show an explicitly labeled interval of at most 2,000
consecutive states to avoid misleading shortcuts across omitted turns.

## Playback smoothness follow-up

The default playback multiplier is 1.0× = **10 ticks/s**, independent of the
recording's `agentMaxCounter`. Legacy timestep plans retain 5 timesteps/s.
The default render callback target is now **60 FPS** (previously 30); adjacent
positions/headings remain interpolated and event/task state uses integer time.
Deterministic checks at 30, 60, and 120 requested FPS all advance exactly ten
logical ticks per elapsed second, within floating-point tolerance.

Profiling identified large antialiased compound paths, per-frame task rectangle
construction, and whole-task-table invalidation as avoidable frame costs.
Opaque circles/headings now use Qt ellipse primitives; translucent overlaps keep
their original winding-fill semantics. Visible task rectangles are cached and
batched in their original overlap order. Unchanged analytics marker lists are
reused. The task table indexes release/assignment/completion transitions and
emits updates only for rows whose displayed values changed, including reverse
and skipped seeks. No global garbage-collector settings were changed.

The playback follow-up suite passed **81 tests** (4.847 seconds), including two new
fractional-playback/cache integration tests, two pixel-level overlap tests, and
eight transition/proxy-filter tests. The warehouse screenshot was inspected.

Serial offscreen paint samples used a fitted 1004 × 720 map viewport in a
1440 × 900 window and rendered into an ARGB32 premultiplied QImage. The baseline
renderer was taken from the temporary wheel installed during migration. Both
versions used the same fixtures and view options. Baseline used 30 samples,
updated renderer 100; times include scene painting, not desktop presentation.

| Fixture | Before median / p95 | After median / p95 |
| --- | ---: | ---: |
| Warehouse, 200 agents | 16.28 / 16.70 ms | 1.99 / 2.27 ms |
| Iron, 10,000 agents + 20,000 task markers | 32.36 / 32.91 ms | 11.87 / 12.89 ms |

At actual iron ticks 100–119, reusing the rectangles themselves further reduced
transition-frame painting from 21.80 to 15.16 ms median and 38.79 to 16.42 ms
p95 (before/after this final cache improvement). This measurement includes
changing task markers, unlike the steady-scene paint samples above.

A separate serial whole-window event-loop smoke used 1320 × 880 windows,
approximately two seconds of playback from tick 100 per case, full teams,
10 ticks/s and a 60 FPS target for **both** versions. It measured the intervals
between map viewport paint events, including the effects of tick updates:

| Case | Before paint interval median / p95 | After paint interval median / p95 |
| --- | ---: | ---: |
| Warehouse | 17.81 / 19.60 ms | 17.02 / 18.02 ms |
| Iron | 35.11 / 51.53 ms | 17.68 / 34.89 ms |
| Iron, Tasks tab with `assigned` filter | 128.36 / 132.32 ms | 17.72 / 34.94 ms |

These short event-loop samples show improvement and remaining long frames;
paint-event intervals are not native display presentation measurements.

Filtered task-table updates were also checked against domain states on real
fixtures over forward, backward, and skipped seeks. In the iron tick 100–119
sample, the table invalidated 482 rows instead of all 205,060 row instances.
The one-tick assignment color remains a renderer concern; the table displays
`assigned` and therefore does not invalidate solely at assignment + 1.

These are local offscreen measurements, not a guarantee of 60 FPS on the native
desktop. Large scenes, task transitions, labels at high zoom, and other visible
windows can still lengthen frames. The user's exact input and display setup
were not supplied for this check.

## Input converter follow-up

Inputs now pass through an explicit converter registry. LoRR 2023, 2024 and
2026 have separate converter IDs and version contracts, sharing their normalized
motion/task decoder. Each supports MAPF and MAPF_T. A fourth converter reads
versioned PlanViz JSON, the common output defined in `INPUT_FORMAT.md`.
New MovingAI-specific result formats were explicitly deferred.

The complete suite passed **108 tests** in 9.858 seconds. Added coverage includes:

- All three LoRR versions × both movement models, with independently specified
  states and task completion times; automatic and explicit dispatch agree.
- Versionless empty tick paths, sequential tasks without a schedule, static
  2023 inputs, conflicting overrides, ambiguous detection, and custom converters.
- All 12 repository LoRR fixtures at full team sizes converted to common JSON
  and decoded again. Compressed actual/planned sequences, sampled states,
  tasks, event IDs, conflicts, delays and JSON metadata values are preserved.
- A billion-tick execution exports to less than 500 bytes and reloads into less
  than 1,000 bytes of path storage, without expansion into per-tick states.
- CLI format listing, inspection and normalization with Qt imports explicitly
  forbidden; desktop format selection, worker propagation, normalized export,
  full loaded timeline preservation and output I/O error handling.

The default render rate and playback speed remain 60 FPS target and 10 ticks/s.
This work establishes converter and common-output support; it does not address
the previously identified gaps in full legacy UI feature parity.

A new wheel built successfully with the converter packages included. Running
directly from that wheel outside the repository normalized a two-agent 2026
fixture and reopened it with `--format planviz --inspect`; the full 5,000-tick
timeline and finite initial/middle/final states were retained. Build artifacts
were removed from the source tree after verification.

## Converter package and authoring guide

Converter implementations now live together in `src/planviz_qt/converters/`.
Its `README.md` explains the contract, source semantics, registration,
CLI usage, and tests; `FORMAT.md` defines the common JSON output. The opt-in
`ExampleConverter` is executable but is not registered among built-in formats.
Previous `io` converter import paths remain compatibility facades.

The complete suite passed **114 tests** in 9.223 seconds. Six example tests cover
both movement models, private registration, malformed inputs, empty paths,
team filtering with full timeline preservation, progress, and cancellation.
The README's Python example successfully generated normalized JSON.

A wheel built successfully with both converter documents and the example
included. Documentation links and the `planviz-convert` entry point were
checked. Executing the new module directly from the wheel outside the source
tree normalized a two-agent 2026 fixture and reopened it with `--inspect`;
the full 5,000-tick timeline and finite sampled states were preserved.

## Visual settings window

Map display controls are grouped in one reusable modeless `Visual settings`
dialog, opened from the toolbar or View menu. Path, planned-state, and task
display controls no longer occupy the Inspector. Settings apply immediately
and survive dialog closure and plan replacement within the same main window.
The optional hover location badge uses one mouse-transparent viewport label;
invalid coordinates, leaving the viewport, and plan replacement clear it.

The complete suite passed **119 tests** in 9.903 seconds. New checks cover live
layer/action synchronization, reopening/reloading, task display semantics,
selected paths, planned states, hover boundaries and scene item counts. A
keyboard regression check ensures Space and arrow input in the dialog do not
trigger playback shortcuts, and Escape restores map keyboard interaction.

Offscreen Fusion renders were inspected with light and dark palettes. The
360 × 520 settings dialog fits alongside the supported minimum 900 × 620 main
window size; the toolbar entry is visible and display controls are absent from
the Inspector. These are offscreen UI checks, not native macOS presentation
or accessibility-service verification.

## Agent indices at Fit map

The checkbox correctly updated the action and renderer option, but agent IDs
were suppressed below 24 screen pixels per cell. The real 200-agent warehouse
fixture fits at 15.088 pixels/cell in the default window and 8.439 pixels/cell
at the minimum size, so toggling the setting previously produced no pixel
change. Agent IDs now honor the checkbox at every zoom and use screen-space
text without cell-sized clipping. Text layout is cached by agent for the
current font size and cleared on plan replacement; scene batching and agent
viewport culling are preserved.

The complete suite passed **121 tests** in 9.817 seconds. New regression checks
toggle the actual dialog control and compare fitted viewport pixels, and
verify that a five-digit ID remains visible and unclipped below 10 pixels/cell.
The fitted warehouse screenshot was inspected with indices enabled.

Local offscreen paint medians (12 warm samples after four warmups, default
1320 × 880 main window) were 1.83 ms without IDs / 2.14 ms with IDs for the
200-agent warehouse, and 11.60 ms / 32.56 ms for the 10,000-agent iron fixture.
These are scene paint samples, not native presentation rates. At dense overview
zoom, showing every ID can overlap labels and cost additional frame time;
the tooltip explains that zooming separates crowded labels.

## Start-location rendering cache

Enabling start locations previously rebuilt and rasterized a stroked compound
path on every frame, although those positions never move. The renderer now
retains one transparent image of the visible start markers. Camera transforms,
exposure, render scale/DPR, and plan replacement invalidate it; playback and
off/on toggles reuse it. The cache is bounded to the rendered visible region,
not the map dimensions. Winding-fill overlap and original layer ordering are
preserved. First display and camera changes still pay the rasterization cost.

The complete suite passed **125 tests**. Four new checks cover reuse during
moving frames, toggles, camera/reload invalidation, exact coincident center
translucency, and cached/direct images at DPR 1/2 and different export sizes.
The transparent intermediate introduces at most 3/255 channel rounding on
fewer than 0.5% of pixels in the antialiased reference fixtures. The actual
warehouse view with starts and agent indices enabled was visually inspected.

Controlled serial before/after runs used the same original renderer snapshot,
inputs, tick 100, 1320 × 880 main window, 864 × 680 viewport, and fitted camera.
Agent indices were off to isolate start markers; grid/headings and assigned
task display were on, with no selection. Each case used four warmups and 40
`QGraphicsView.render()` samples into a viewport-sized QImage.

| Fixture, starts enabled | Before median / p95 | Cached median / p95 |
| --- | ---: | ---: |
| Warehouse, 200 agents | 15.46 / 16.44 ms | 1.88 / 2.07 ms |
| Iron, 10,000 agents | 28.60 / 30.19 ms | 11.80 / 13.06 ms |

First enabled paints after the change were 15.71 ms and 31.15 ms respectively;
with starts disabled, updated medians were 1.79 ms and 11.69 ms. An earlier
warehouse run had substantial timing variance, so only the later controlled
comparison is tabulated. These samples exclude frame computation, event-loop
work, and native display presentation; they do not establish an application FPS.

## Configurable palette, legend, and task/errand shapes

The packaged `palettes/Color_palette.yaml` is the single default-color source
for agents, task destinations, intermediate errands, and paths. A Qt-independent
loader merges partial overrides, normalizes case, and rejects invalid colors,
versions, tags, duplicate keys, unknown keys, and incomplete bundled defaults.
PyYAML 6.0.3 was installed in the project environment and added to requirements.
The modeless Colors & legend window shows all 23 configured values and shapes,
loads/reloads YAML, saves an active editable copy, and restores defaults. Invalid
loads leave the current palette intact; successful changes preserve playback,
selection, and the loaded plan. CLI `--palette` validation remains Qt-free.

Analytics now provides semantic kind/state/release time instead of hardcoded
colors. Agents remain circles, final task destinations are squares, and
intermediate errands are diamonds. Shared-location map markers are coalesced
by the maximum `(release_time, task_id, stop_index)` among currently supplied
markers, with `*` only when distinct task IDs overlap. Domain records and the
full remaining-stop arrow sequence are retained. Generic color-only layers
preserve their paint order. Integer-grid semantic markers batch by color and
shape; screen-space task labels and start-location rasters retain their caches.

The full suite passed **152 tests**. Added checks include palette validation
and safe saving, live legend updates, UI load/reload/save/failure behavior,
recorded-state color priority, CLI validation without Qt, square/diamond pixels,
deterministic overlap/filter behavior, and preservation of rendering caches.
One initial integration assertion was corrected to compare resolved macOS
temporary-file paths (`/var` versus `/private/var`); no application defect was
involved in that failure.

All legend tabs were inspected in light and dark offscreen Fusion palettes at
580 × 560, including actual map-background samples for dark text colors. Toolbar
access was checked at the minimum 900 × 620 main-window size. A custom idle
color, visible task/errand shapes, and a shared-cell `29:2*` marker were inspected.
A wheel built with the YAML resource and PyYAML dependency, loaded/saved its
palette and opened the legend offscreen outside the repository. Build artifacts
were removed from the source tree.

A serial warm-paint smoke at tick 100 (same settings as the preceding start
cache benchmark, 40 samples, agent/task indices off) measured starts-off/on
medians of 1.87/1.92 ms for warehouse 200 and 15.05/15.56 ms for iron 10,000.
The new diamond geometry differs from earlier square-only rendering; these
samples verify bounded start-marker overhead, not an application FPS guarantee.

## Path service, label caching, and input diagnostics — 2026-09-09

The complete suite passed **165 tests in 10.188 seconds** with offscreen Qt.
Changes are confined to the separate Qt application. Selected-path calculation
now lives in a GUI-independent service with bounded block/arrival caches. The
renderer reuses simplified path geometry, and interpolated frames retain their
logical tick's agent colors. Agent IDs use a bounded raster cache with direct
text fallback when its budget is exhausted.

New checks compare actual and planned route geometry against consecutive sampled
states for MAPF and MAPF_T, including turns, waits, reversals, block boundaries,
backward seeks, first arrivals, playback limits, and static paths. A billion-tick
compressed fixture verifies bounded decoding and memory during repeated advances.
Application tests verify geometry reuse and unchanged selected-path intervals.
Scene checks cover label cache reuse/invalidation across zoom, palette and DPR
1/2, and continued label visibility with no raster budget. Warehouse viewport
renders at DPR 1 and 2 were visually inspected with IDs, a red selection outline,
and the path to the next errand visible. These are offscreen images, not native
desktop interaction checks.

Malformed map headers/dimensions and noninteger LoRR count/duration fields now
fail loading. Task timing inconsistencies become aggregated warnings while
original histories/events remain intact. Tests cover that boundary, valid records,
and monotonic loading progress. The warehouse fixture reports 200 out-of-range
assignments and 400 completions without matching assignments; no timestamps or
ownership records were repaired. See [input validation policy](VALIDATION_POLICY.md).

A separate serial benchmark measured warehouse 20-agent selection updates at
6.69 → 0.96 ms median and iron 10,000-agent painting with IDs at 31.00 → 21.18 ms.
The [benchmark report](benchmarks/README.md) includes all cases, raw data,
reproduction commands, cold-cache costs, and remaining task-transition latency.
These improvements do not establish native 60 FPS or exhaustive equivalence of
every possible input. No new wheel build or Windows/Linux desktop validation was
performed in this pass.
