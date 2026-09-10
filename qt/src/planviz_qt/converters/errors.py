"""Input failures shared by converters and application-facing loaders."""


class PlanLoadError(ValueError):
    """An input file cannot be interpreted as a plan."""


class LoadCancelled(InterruptedError):
    """The caller cancelled loading."""


class ConversionError(ValueError):
    """Malformed source data prevents a reliable conversion."""
