"""Nonfatal consistency diagnostics; records are retained for inspection."""
from bisect import bisect_right
from collections import Counter


def record_warnings(plan, *, cancelled=None):
    """Report timing inconsistencies without inventing or shifting events.

    Future task releases are legitimate. Recorded assignments/completions beyond
    the replay range, however, are reported. Findings are aggregated so a large
    broken log does not produce an unbounded warning list.
    """
    findings = Counter()
    for index, task in enumerate(plan.tasks):
        if index % 1024 == 0 and cancelled is not None and cancelled():
            raise InterruptedError("Plan checking cancelled.")
        assignments = tuple(sorted(task.assignments))
        times = tuple(at for at, _ in assignments)
        for at, _agent in assignments:
            if at > plan.max_time:
                findings['Assignments beyond the replay range'] += 1
            if at < task.release_time:
                findings['Assignments before task release'] += 1
        for at, agent, _stop in task.completions:
            if at > plan.max_time:
                findings['Completions beyond the replay range'] += 1
            if at < task.release_time:
                findings['Completions before task release'] += 1
            index = bisect_right(times, at)-1
            if index < 0 or assignments[index][1] != agent:
                findings['Completions without a matching assignment at that time'] += 1
    return tuple(f"{name}: {count:,}. Original records were retained."
                 for name, count in findings.items())
