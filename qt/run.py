"""Run the standalone source checkout without installing it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from planviz_qt.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
