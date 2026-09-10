"""Validated YAML palettes shared by Qt rendering and GUI-independent tools."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping

import yaml
from yaml.nodes import MappingNode, ScalarNode


_SCHEMA_VERSION = 1
_SECTION_KEYS = {
    "agent": frozenset(("idle", "newly_assigned", "delayed", "errand_completed", "collision",
                        "heading", "index", "selected_outline", "collision_outline",
                        "start_fill", "start_outline")),
    "task": frozenset(("unassigned", "newly_assigned", "assigned", "completed", "index")),
    "errand": frozenset(("unassigned", "newly_assigned", "assigned", "completed", "index")),
    "path": frozenset(("executed", "remaining_errands")),
}
_SECTIONS = tuple(_SECTION_KEYS)
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_YAML_MAP = "tag:yaml.org,2002:map"
_YAML_STRING = "tag:yaml.org,2002:str"
_YAML_INTEGER = "tag:yaml.org,2002:int"


class PaletteError(ValueError):
    """A palette cannot be read, validated, or written."""


@dataclass(frozen=True)
class Palette:
    """Immutable color selections and their optional custom source file.

    Use ``load_palette`` to construct a validated instance. Colors are plain
    strings so loading and saving never requires a GUI framework.
    """

    _sections: Mapping[str, Mapping[str, str]]
    source: Path | None = None

    def __post_init__(self):
        # A frozen dataclass alone would leave nested dictionaries mutable.
        object.__setattr__(self, "_sections", MappingProxyType({
            section: MappingProxyType(dict(colors)) for section, colors in self._sections.items()
        }))

    def color(self, section: str, key: str) -> str:
        """Return one normalized #rrggbb color; names are case-insensitive."""
        if not isinstance(section, str) or not isinstance(key, str):
            raise PaletteError("Palette section and color key must be strings.")
        try:
            return self._sections[section.casefold()][key.casefold()]
        except KeyError as exc:
            raise PaletteError(f"Unknown palette color {section}.{key}.") from exc

    def as_dict(self) -> dict:
        """Return the full schema as a detached, serializable dictionary."""
        return {"version": _SCHEMA_VERSION,
                **{section: dict(colors) for section, colors in self._sections.items()}}


def _mapping(node, label):
    if not isinstance(node, MappingNode) or node.tag != _YAML_MAP:
        raise PaletteError(f"{label} must be a plain YAML mapping; custom tags are not supported.")
    result = {}
    for key_node, value_node in node.value:
        if not isinstance(key_node, ScalarNode) or key_node.tag != _YAML_STRING:
            raise PaletteError(f"{label} keys must be strings; custom tags and YAML merge keys are not supported.")
        key = key_node.value.casefold()
        if key in result:
            raise PaletteError(f"{label} contains duplicate key {key_node.value!r} (names are case-insensitive).")
        result[key] = value_node
    return result


def _decode(text, *, defaults=None):
    # Inspect safe YAML nodes directly: no constructors (including custom
    # object constructors) execute, and quote style remains available.
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        raise PaletteError(f"Invalid YAML: {exc}") from exc
    fields = _mapping(root, "Palette")
    unknown = set(fields) - {"version", *_SECTIONS}
    if unknown:
        raise PaletteError(f"Unknown palette section: {', '.join(sorted(unknown))}.")
    version = fields.get("version")
    if version is None:
        if defaults is None:
            raise PaletteError("Bundled palette must declare version: 1.")
    elif not (isinstance(version, ScalarNode) and version.tag == _YAML_INTEGER
              and version.value == str(_SCHEMA_VERSION)):
        raise PaletteError("Palette version must be the integer 1.")
    result = {section: dict(defaults[section]) if defaults is not None else {}
              for section in _SECTIONS}
    for section in _SECTIONS:
        if section not in fields:
            if defaults is None:
                raise PaletteError(f"Bundled palette is missing section {section!r}.")
            continue
        colors = _mapping(fields[section], f"Palette.{section}")
        unknown = set(colors) - _SECTION_KEYS[section]
        if unknown:
            raise PaletteError(f"Unknown color in {section}: {', '.join(sorted(unknown))}.")
        if defaults is None:
            missing = _SECTION_KEYS[section] - set(colors)
            if missing:
                raise PaletteError(f"Full palette is missing colors in {section}: {', '.join(sorted(missing))}.")
        for key, value in colors.items():
            if not (isinstance(value, ScalarNode) and value.tag == _YAML_STRING
                    and value.style in ("'", '"') and _COLOR.fullmatch(value.value)):
                raise PaletteError(f"{section}.{key} must be a quoted hexadecimal color such as \"#342353\".")
            result[section][key] = value.value.lower()
    return result


def load_palette(path: str | Path | None = None) -> Palette:
    """Load defaults, or merge a partial custom YAML palette over defaults.

    Defaults come from package resources, making wheel installations independent
    of the working directory. Reading the resource on each call also lets a
    source checkout use edits to the bundled YAML without restarting Python.
    """
    try:
        text = resources.files("planviz_qt.palettes").joinpath("Color_palette.yaml").read_text(encoding="utf-8")
        defaults = _decode(text)
    except (OSError, UnicodeError, PaletteError) as exc:
        raise PaletteError(f"Cannot load bundled Color_palette.yaml: {exc}") from exc
    if path is None:
        return Palette(defaults)
    source = Path(path).expanduser().resolve()
    try:
        colors = _decode(source.read_text(encoding="utf-8"), defaults=defaults)
    except (OSError, UnicodeError, PaletteError) as exc:
        raise PaletteError(f"Cannot load palette {source}: {exc}") from exc
    return Palette(colors, source)


def save_palette(palette: Palette, path: str | Path) -> None:
    """Save a complete, quoted-color YAML copy without changing its source."""
    destination = Path(path).expanduser()
    try:
        text = yaml.safe_dump(palette.as_dict(), sort_keys=False, allow_unicode=True)
        # Defend the public constructor too: an invalid manually constructed
        # Palette must not overwrite a previously valid file.
        _decode(text)
        destination.write_text(text, encoding="utf-8")
    except (OSError, UnicodeError, yaml.YAMLError, PaletteError) as exc:
        raise PaletteError(f"Cannot save palette {destination}: {exc}") from exc
