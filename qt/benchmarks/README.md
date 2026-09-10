# Replay optimization measurements — 2026-09-09

These measurements compare the application immediately before and after the
selected-path and agent-label optimizations. They are local CPU-side samples,
not native desktop FPS or a guarantee for other hardware and inputs.

## Reproduce

From the repository root, with GUI dependencies installed, run separately from
the test suite and other CPU-intensive work:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=qt/src .venv/bin/python -B \
  qt/benchmarks/replay.py > /tmp/planviz-replay.jsonl
```

Use `python` instead of `.venv/bin/python` in another environment. Optional
`--samples` and `--warmup` arguments default to 20 and 4. The script measures the
current implementation; [baseline.jsonl](baseline.jsonl) preserves the readings
captured before these changes. [optimized.jsonl](optimized.jsonl) contains the
final measurements. [environment.json](environment.json) records runtime versions
and SHA-256 hashes of the fixture inputs.

The measured environment used macOS 26.6.2, Python 3.12.13, PySide6/Qt 6.11.1,
and NumPy 2.2.6. Both fixtures used the default window, an 864 × 710 logical-pixel
viewport, a fitted camera, assigned tasks, and no start markers. Task indices
were disabled. The 20-agent selection contains IDs 0 through 19. The transient
selection pulse was stopped to keep its animation phase out of the comparison.

Each case seeks through consecutive ticks, with four warmups followed by 20
measurements: warehouse ticks 1005–1024 and iron ticks 905–924. A seek includes
logical state, Inspector, task, path, and rendered-position updates. Paint is
measured separately with `QGraphicsView.render()` into a viewport-sized QImage.
Neither timing includes native window presentation, vsync, or a continuously
running playback event loop. Values below are medians, in milliseconds.

## Before and after

| Fixture | Agent IDs | Selected agents | Tick update, before → after | Paint, before → after |
| --- | --- | ---: | ---: | ---: |
| Warehouse, 200 agents | Off | 0 | 0.32 → 0.40 | 1.85 → 1.99 |
| Warehouse, 200 agents | On | 0 | 0.39 → 0.36 | 2.25 → 2.17 |
| Warehouse, 200 agents | Off | 20 | 6.69 → 0.96 | 4.98 → 4.77 |
| Iron, 10,000 agents | Off | 0 | 5.79 → 5.74 | 12.44 → 12.54 |
| Iron, 10,000 agents | On | 0 | 5.79 → 6.04 | 31.00 → 21.18 |
| Iron, 10,000 agents | Off | 20 | 7.64 → 6.36 | 10.78 → 10.65 |

The warehouse selection case reduced median update time by about 86%; the iron
ID case reduced median painting time by about 32%. Small unselected cases changed
little and some readings increased. The experiment does not establish a general
speedup for all options, time ranges, or machines.

Loading and indexing took 59.44 → 60.84 ms for warehouse and 686.48 → 701.36 ms
for iron. Loading now includes additional record consistency diagnostics. These
are one sample per fixture, not a loading-time distribution. Compressed path
storage remained 2.61 MiB and 11.73 MiB, respectively; it excludes other memory.

## Why the changes help

`domain/selection.py` retains consecutive path samples in fixed 256-tick blocks,
instead of decoding an overlapping 2,000-state window on every tick. The cache
holds at most 128 blocks and 128 target-arrival entries. At the default window
size, each block contains at most 2,255 states per actual/planned trajectory.
The planned trajectory is populated only if requested. Straight interior points
are removed from the drawing, while turns, reversals, and wait boundaries remain
available when clipping the route. The renderer reuses interior Qt geometry and
moves only its endpoints while the segment configuration is unchanged.

Across the measured 20-agent cases, warehouse retained 40 blocks / 2.10 MiB and
iron retained 20 blocks / 0.13 MiB. Warehouse crosses a block boundary during the
sample. These byte counts include cached sample, corner-index, and arrival-index
arrays, but exclude Python object overhead and the displayed Qt geometry. More
selected agents than the cache can hold may cause eviction and repeated decoding.

`ui/text_cache.py` retains rasterized agent IDs and reuses them while positions
move. Font, color, and device pixel ratio changes invalidate the cache. The
renderer also computes label positions in batches and updates agent colors only
at logical ticks, reusing them for interpolated frames.

## Costs and remaining bottlenecks

- Raster labels used about 0.17 MiB for warehouse and 12.99 MiB for iron in this
  viewport. The pixel budget is 96 MiB, excluding Qt/Python bookkeeping and text
  layouts. At the budget limit, uncached IDs use direct text rendering; no IDs
  are hidden. Higher pixel density consumes more storage.
- A separate first paint with both label caches empty took 4.55 ms for warehouse
  and 172.37 ms for iron. Enabling many labels for the first time, changing their
  font size, changing palette, or moving between screen densities can cause a
  visible pause. Warm-cache figures do not include this construction cost.
- Iron tick-update p95 was 65.23 ms without IDs and 70.89 ms with IDs. Profiling
  the same interval identified task-marker reconstruction at task transitions
  (`_refresh_tasks` / `set_tasks` / `_coalesce_task_markers`) as the dominant work.
  Non-transition ticks reuse the marker list. Selection limits the displayed task
  set, explaining why the 20-agent case has a lower p95 (6.76 ms). The baseline
  did not record update p95, so there is no before/after tail-latency claim.
- Showing every ID at dense overview zoom still causes overlap and costs more
  than the 16.7 ms paint budget for 60 FPS in the iron case. Task transitions and
  event-loop work add further latency. Continuous native 60 FPS is not established.

Further task-transition work should update affected marker locations and preserve
the latest-task / asterisk overlap rule, rather than rebuild all markers. A label
atlas or incremental raster preparation could address cold-cache latency. Those
are distinct future changes that require their own measurements and regression
checks; they are not implemented by this optimization pass.
