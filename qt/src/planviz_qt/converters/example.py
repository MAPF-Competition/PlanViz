"""Small, opt-in converter example; see README.md in this directory.

The source schema uses consecutive timestep actions and row/column coordinates.
It does not accept timed samples, planner histories, or task records. Unknown
fields are rejected so an extension cannot silently lose their semantics.
"""
from __future__ import annotations

from ..domain.models import PlanData
from .base import ConversionContext
from .exchange import decode_document
from .motions import parse_motion_sequence


class ExampleConverter:
    """Translate ``example-actions`` JSON into the common normalized contract.

    This class is deliberately not registered by default. The documentation
    demonstrates both a private registry and registration for the CLI/desktop.
    """

    id = "example-actions"
    label = "Example timestep actions"

    def can_read(self, data: dict) -> bool:
        return isinstance(data, dict) and data.get("format") == self.id

    def convert(self, data: dict, context: ConversionContext) -> PlanData:
        context.checkpoint(15, "Validating example actions")
        if not self.can_read(data):
            raise ValueError("ExampleConverter requires format = 'example-actions'.")
        unknown = set(data) - {"format", "action_model", "starts", "actions", "metadata"}
        if unknown:
            raise ValueError("Unsupported example-actions fields: " + ", ".join(sorted(unknown))
                             + ". Put annotations in metadata; timing/planner/task fields need an explicit adapter.")
        model = data.get("action_model")
        if model not in ("MAPF", "MAPF_T"):
            raise ValueError("action_model must be 'MAPF' or 'MAPF_T'.")
        starts, actions = data.get("starts"), data.get("actions")
        if not isinstance(starts, list) or not isinstance(actions, list):
            raise ValueError("starts and actions must be arrays.")
        if len(starts) != len(actions):
            raise ValueError("starts and actions must contain the same number of agents.")
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object.")
        metadata = {**metadata, "source": str(context.source)}
        agents, max_time = [], 0
        for agent, (start, text) in enumerate(zip(starts, actions)):
            if agent % 64 == 0:
                context.checkpoint(20 + 35 * agent // max(1, len(starts)),
                                   f"Converting example agent {agent + 1}/{len(starts)}")
            if isinstance(text, str) and text.lstrip().startswith("[("):
                raise ValueError(f"actions[{agent}] requires timestep actions, not segmented RLE ticks.")
            sequence = parse_motion_sequence(text, action_model=model, label=f"actions[{agent}]")
            max_time = max(max_time, sequence.length)
            agents.append({"start": start, "actual": [list(run) for run in
                                                       zip(sequence.actions, sequence.durations)]})
        document = {
            "format": "planviz", "schema_version": 1,
            "source_version": "Example actions", "action_model": model,
            "time_unit": "timestep", "ticks_per_step": 1, "max_time": max_time,
            "map": {"width": context.map_data.width, "height": context.map_data.height},
            "agents": agents, "tasks": [], "events": [], "conflicts": [],
            "delays": {}, "metadata": metadata,
        }
        # Shared validation checks every agent before filtering, preserves the
        # complete timeline, and builds compressed paths without expanding time.
        return decode_document(
            document, context.map_data, team_size=context.team_size,
            cancelled=context.cancelled,
            progress=lambda percent, message: context.checkpoint(60 + percent * 40 // 100, message),
        )
