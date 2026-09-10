"""Compatibility import; implementation lives in planviz_qt.converters."""
from ..converters import ConversionError, convert_paths, convert_tracker, main

if __name__ == "__main__":
    raise SystemExit(main())
