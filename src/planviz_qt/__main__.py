"""Desktop entry point and a GUI-free loading diagnostic."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


def boolean(value):
    if isinstance(value, bool):
        return value
    if value.lower() in ("yes", "true", "1", "on"):
        return True
    if value.lower() in ("no", "false", "0", "off"):
        return False
    raise argparse.ArgumentTypeError("Expected true or false")


def build_parser():
    from planviz_qt.converters.registry import available_formats
    parser = argparse.ArgumentParser(description="PlanViz Qt — inspect multi-agent plans and execution logs")
    parser.add_argument("--map", help="MovingAI .map file")
    parser.add_argument("--plan", help="PlanViz / LoRR JSON solution")
    parser.add_argument("--format", choices=("auto", *(identifier for identifier, _ in available_formats())),
                        default="auto", help="Input converter (default: auto)")
    parser.add_argument("--list-formats", action="store_true", help="List input converters without importing Qt")
    parser.add_argument("--version", choices=("2023 LoRR", "2024 LoRR", "2026 LoRR"),
                        help="Legacy LoRR version override; must agree with --format")
    parser.add_argument("--n", type=int, help="Load the first N agents")
    parser.add_argument("--start", type=int, default=0, help="First visible tick/timestep")
    parser.add_argument("--end", type=int, help="Last visible tick/timestep")
    parser.add_argument("--fps", type=int, default=60, help="Target render callback rate (default: 60)")
    parser.add_argument("--speed", type=float,
                        help="Playback multiplier (default: 1.0; 1× = 10 ticks/s or 5 legacy timesteps/s)")
    parser.add_argument("--event-limit", type=int, default=100, help="Maximum recent event rows (default: 100)")
    for flag, description, default in (("grid", "Grid", True), ("aid", "Agent IDs", True), ("tid", "Task IDs", False)):
        parser.add_argument(f"--{flag}", type=boolean, nargs="?", const=True, default=default, help=f"{description}: true/false")
    parser.add_argument("--static", action="store_true", help="Show start locations")
    parser.add_argument("--ca", action="store_true", help="Highlight colliding agents")
    parser.add_argument("--palette", help="Custom color palette YAML; unspecified colors use bundled defaults")
    parser.add_argument("--hm", nargs="+", default=[], help="Traffic heatmap solution files")
    parser.add_argument("--hw", help="Highway direction file")
    parser.add_argument("--heu", help="Heuristic values file")
    parser.add_argument("--searchTree", nargs="+", default=[], help="Search-tree files")
    parser.add_argument("--inspect", action="store_true", help="Load, validate and print JSON statistics without importing Qt")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_formats:
        from planviz_qt.converters.registry import available_formats
        print("auto\tAuto-detect")
        for identifier, label in available_formats():
            print(f"{identifier}\t{label}")
        return 0
    if bool(args.map) != bool(args.plan):
        parser.error("--map and --plan must be provided together")
    if args.inspect and not args.plan:
        parser.error("--inspect requires --map and --plan")
    if args.n is not None and args.n <= 0:
        parser.error("--n must be positive")
    if args.start < 0 or (args.end is not None and args.end < args.start):
        parser.error("Expected 0 <= --start <= --end")
    if args.fps < 1 or args.fps > 240 or args.event_limit < 1:
        parser.error("--fps must be between 1 and 240; --event-limit must be positive")
    if args.speed is not None:
        import math
        if not math.isfinite(args.speed) or args.speed <= 0:
            parser.error("--speed must be finite and positive")
    palette = None
    if args.palette:
        from planviz_qt.palette import load_palette
        try:
            palette = load_palette(args.palette)
        except (OSError, ValueError) as error:
            parser.exit(2, f"Cannot load palette: {error}\n")
    if args.inspect:
        from planviz_qt.io.loader import load_plan
        from planviz_qt.domain.analytics import AnalyticsIndex
        started = time.perf_counter()
        try:
            plan = load_plan(args.map, args.plan, version=args.version, team_size=args.n,
                             input_format=args.format)
            index = AnalyticsIndex(plan)
            import numpy as np
            frames = {}
            for tick in sorted({0, plan.max_time//2, plan.max_time}):
                positions = plan.paths.positions(tick)
                frames[str(tick)] = {"shape": list(positions.shape), "finite": bool(np.isfinite(positions).all())}
            print(json.dumps({
                "version": plan.version, "action_model": plan.action_model, "agents": plan.team_size,
                "map": {"width": plan.map.width, "height": plan.map.height},
                "time_unit": plan.time_unit, "max_time": plan.max_time,
                "tasks": len(plan.tasks), "events": len(plan.events), "conflicts": len(plan.conflicts),
                "completed": index.counts(plan.max_time), "path_storage_bytes": plan.paths.storage_bytes,
                "load_and_inspect_seconds": round(time.perf_counter()-started, 4),
                "frames": frames, "warnings": plan.metadata.get("warnings", []),
            }, indent=2))
        except (OSError, ValueError, KeyError) as error:
            parser.exit(1, f"Cannot load solution: {error}\n")
        return 0

    if palette is None:
        from planviz_qt.palette import load_palette
        try:
            palette = load_palette()
        except (OSError, ValueError) as error:
            parser.exit(2, f"Cannot load palette: {error}\n")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from planviz_qt.application.loading import LoadRequest
    from planviz_qt.ui.main_window import MainWindow, ViewOptions
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("PlanViz Qt")
    app.setOrganizationName("PlanViz")
    window = MainWindow(ViewOptions(args.start, args.end, args.fps, args.speed, args.event_limit,
                                   args.grid, args.aid, args.tid, args.static, args.ca), palette=palette)
    window.show()
    if args.plan:
        overlays = [("heatmap", name) for name in args.hm]
        overlays += [("search_tree", name) for name in args.searchTree]
        if args.hw:
            overlays.append(("highway", args.hw))
        if args.heu:
            overlays.append(("heuristic", args.heu))
        request = LoadRequest(str(Path(args.map).resolve()), str(Path(args.plan).resolve()),
                              args.version, args.n, tuple(overlays), args.format)
        QTimer.singleShot(0, lambda: window.load(request))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
