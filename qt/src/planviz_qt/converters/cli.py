"""Command-line entry point for normalized and legacy converter output."""
from __future__ import annotations

import argparse
import csv

from .legacy import convert_paths, convert_tracker, _output_path


def main(argv=None) -> int:
    from planviz_qt.converters.registry import available_formats
    parser = argparse.ArgumentParser(description="Normalize plans or convert legacy tracker and path text inputs.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    normalize = subcommands.add_parser("normalize", help="Convert a supported input to normalized PlanViz JSON.")
    normalize.add_argument("--map", required=True, help="Grid map file.")
    normalize.add_argument("--plan", required=True, help="Input solution JSON.")
    normalize.add_argument("--format", choices=("auto", *(identifier for identifier, _ in available_formats())),
                           default="auto", help="Input converter (default: auto).")
    normalize.add_argument("--version", choices=("2023 LoRR", "2024 LoRR", "2026 LoRR"),
                           help="Legacy LoRR version override; must agree with --format.")
    normalize.add_argument("--output", required=True, help="Normalized output JSON filename.")
    normalize.add_argument("--n", type=int, help="Convert only the first N agents.")
    tracker = subcommands.add_parser("tracker", help="Convert tracker CSV and MovingAI scenario records.")
    tracker.add_argument("--plan", required=True, help="Tracker CSV input.")
    tracker.add_argument("--scen", required=True, help="Scenario file, or folder when --multi is used.")
    tracker.add_argument("--output", required=True, help="Output JSON filename; bulk adds _0, _1, ... suffixes.")
    tracker.add_argument("--multi", action="store_true", help="Read every solution_plan row rather than first path row.")
    paths = subcommands.add_parser("paths", help="Convert Agent N: (row,col)->... coordinate paths.")
    paths.add_argument("--path", required=True, help="Coordinate path text file.")
    paths.add_argument("--output", required=True, help="Output JSON filename.")
    paths.add_argument("--conf", help="Optional conflict CSV (V/E/T types).")
    args = parser.parse_args(argv)
    if args.command == "normalize" and args.n is not None and args.n <= 0:
        parser.error("--n must be positive")
    try:
        if args.command == "normalize":
            from planviz_qt.converters.exchange import dump_plan
            from planviz_qt.io.loader import load_plan
            result = load_plan(args.map, args.plan, input_format=args.format,
                               version=args.version, team_size=args.n)
            target = _output_path(args.output)
            dump_plan(result, target)
            print(f"Normalized {result.team_size} agent paths to {target}.")
        elif args.command == "tracker":
            results = convert_tracker(args.plan, args.scen, args.output, multi=args.multi)
            print(f"Converted {len(results)} plan(s).")
        else:
            result = convert_paths(args.path, args.output, args.conf)
            print(f"Converted {result['teamSize']} agent paths.")
    except (OSError, csv.Error, ValueError) as exc:
        parser.exit(2, f"Conversion failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
