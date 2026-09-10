# Input validation policy

The loader separates structural failures from inconsistent recorded observations.
It does not establish that a planner solution is feasible or collision-free.

## Structural failures

Loading raises `PlanLoadError` when the input cannot be interpreted safely.
Examples include malformed JSON, an unknown or ambiguous format, unsupported
movement models, malformed motion runs, and missing required agent paths.
Individual converters define the checks specific to their source format.

The existing map reader requires `type octile`, positive integer `height` and
`width`, and the `map` separator. Nonblank map rows must match both declared
dimensions. Supported characters remain `@`, `T`, `.`, `S`, and `E`; this change
does not add another MovingAI result converter or broaden terrain support.

The LoRR converter requires integer JSON values for `teamSize`, the selected
`makespan`/`makespanTicks`, and the 2026 `agentMaxCounter`. Booleans, strings and
fractional numbers are rejected rather than coerced. Counts and durations must
be nonnegative; `agentMaxCounter` must be positive. These stricter checks apply
to those fields, not every scalar in every LoRR record. Normalized PlanViz JSON
has its own [schema and validation contract](src/planviz_qt/converters/FORMAT.md).

## Nonfatal record diagnostics

After conversion, `domain/validation.py` checks loaded task histories for:

- Assignments or completions beyond the replay range.
- Assignments or completions before task release.
- Completions whose recorded agent does not match the assignment at that time.

Findings are aggregated by category in `PlanData.metadata["warnings"]`, alongside
converter-provided warnings. The viewer shows them in **Analysis → Solution
details**. Checks run on the loaded records, including any requested agent limit;
they are not a full audit of excluded source records. Future task releases alone
are permitted, since a producer may include tasks that have not yet been reached.

Original task histories and event counts remain unchanged. The loader does not
shift timestamps, discard inconsistent records, or create replacement assignments.
For example, the repository's `warehouse_small_2026.json` contains 200 assignment
records beyond its replay range and 400 completions without matching assignments
at those times. These are displayed as two warnings rather than blocking replay.

The selected-path overlay may use the next recorded completion as a target when
an active assignment is missing. Inspector labels this fallback. It is a display
aid and does not modify task ownership, events, or reported solution results.

## Converter development

Validate a source field before constructing domain records when an invalid value
would make its meaning ambiguous or unsafe. Raise a descriptive `ValueError` or
`PlanLoadError`; the loader presents the failure without replacing the current
successfully loaded plan. Preserve inconsistent observations that still have a
clear interpretation, and attach source-specific warnings when appropriate.

Call `ConversionContext.checkpoint()` during long loops and report monotonic
progress from 0 through 100. The loader maps converter progress into its loading
stages and runs common record diagnostics before reporting Ready. Do not catch
cancellation and continue. JSON decoding itself remains uninterruptible.

See the [converter development guide](src/planviz_qt/converters/README.md) and
the regression cases in `tests/test_validation.py` for concrete examples.
