from __future__ import annotations

import copy
from typing import Any


class GenerationRuntimeContext:
    """Canonical context behavior shared by local and remote runtimes."""

    @staticmethod
    def resolve(context: dict[str, Any], path: str | None, *, default: Any = None) -> Any:
        if not path:
            return context
        value: Any = context
        for part in str(path).split("."):
            if not part:
                continue
            if not isinstance(value, dict):
                return default
            value = value.get(part, default)
        return value

    @staticmethod
    def step_inputs(context: dict[str, Any], mapping: dict[str, Any] | None) -> dict[str, Any]:
        if not mapping:
            return copy.deepcopy(context)
        return {
            str(input_key): GenerationRuntimeContext.resolve(context, str(source_path or ""))
            for input_key, source_path in mapping.items()
        }

    @staticmethod
    def merge_step_outputs(context: dict[str, Any], step_key: str, outputs: dict[str, Any]) -> None:
        snapshot = copy.deepcopy(outputs)
        context[step_key] = snapshot
        context.update(copy.deepcopy(outputs))

    @staticmethod
    def resolve_module_outputs(
        definitions: list[dict[str, Any]], context: dict[str, Any]
    ) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        for definition in sorted(definitions, key=lambda row: row["position"]):
            source_step_key = definition.get("source_step_key")
            value: Any = context.get(source_step_key) if source_step_key else context
            source_path = definition.get("source_path")
            if source_path:
                value = GenerationRuntimeContext.resolve(
                    value if isinstance(value, dict) else {}, source_path
                )
            if value is None:
                value = context.get(definition["key"])
            outputs[definition["key"]] = value
        return outputs
