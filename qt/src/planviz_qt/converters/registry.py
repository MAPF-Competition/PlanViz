"""Explicit converter registration and structural JSON format detection."""
from __future__ import annotations

from .base import InputConverter
from .exchange import PlanVizConverter
from .lorr import LoRR2023Converter, LoRR2024Converter, LoRR2026Converter


class ConverterRegistry:
    def __init__(self, converters=()):
        self._converters: dict[str, InputConverter] = {}
        for converter in converters:
            self.register(converter)

    def register(self, converter: InputConverter) -> None:
        if not isinstance(converter.id, str) or not converter.id or converter.id == "auto":
            raise ValueError("A converter needs a nonempty ID other than 'auto'.")
        if converter.id in self._converters:
            raise ValueError(f"Converter {converter.id!r} is already registered.")
        self._converters[converter.id] = converter

    @property
    def formats(self) -> tuple[tuple[str, str], ...]:
        return tuple((converter.id, converter.label) for converter in self._converters.values())

    def resolve(self, data: dict, input_format: str = "auto") -> InputConverter:
        if input_format != "auto":
            if input_format not in self._converters:
                raise ValueError(f"Unknown input format {input_format!r}; choose from "
                                 + ", ".join(self._converters))
            return self._converters[input_format]
        matches = [converter for converter in self._converters.values() if converter.can_read(data)]
        if len(matches) > 1:
            raise ValueError("Ambiguous input format; select --format explicitly: "
                             + ", ".join(converter.id for converter in matches))
        if not matches:
            raise ValueError("Unrecognized input format or version. Supported converters: "
                             + ", ".join(self._converters)
                             + ". Select --format when the source has no version tag.")
        return matches[0]


def default_registry() -> ConverterRegistry:
    return ConverterRegistry((LoRR2023Converter(), LoRR2024Converter(),
                              LoRR2026Converter(), PlanVizConverter()))


def available_formats() -> tuple[tuple[str, str], ...]:
    return default_registry().formats
