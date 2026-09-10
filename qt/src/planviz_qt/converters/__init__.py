"""Public converter API, independent of Qt and filesystem dispatch."""

from .base import ConversionContext, InputConverter
from .errors import ConversionError, LoadCancelled, PlanLoadError
from .exchange import decode_document, dump_plan, plan_to_document
from .legacy import convert_paths, convert_tracker
from .registry import ConverterRegistry, available_formats, default_registry


def main(argv=None):
    from .cli import main as run
    return run(argv)


__all__ = ["ConversionContext", "InputConverter", "ConversionError", "LoadCancelled",
           "PlanLoadError", "decode_document", "dump_plan", "plan_to_document",
           "convert_paths", "convert_tracker", "ConverterRegistry", "available_formats",
           "default_registry", "main"]
