from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

_HEX_SUFFIX_RE = re.compile(r"(?i)(?:[_-]?[0-9a-f]{32,128})$")
_PROVIDER_SUFFIX_RE = re.compile(r"\s*\(([^()]*)\)\s*$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class RuntimeAliasResolver:
    """Resolve workflow node names against the static ComfyUI knowledge index.

    ComfyUI workflows may store a public class key, a display label, a Python
    class name, a provider-decorated label, or a generated key with a hash.
    This resolver compares all of those representations without executing
    third-party node code.
    """

    def __init__(self, classes: Iterable[dict[str, Any]]) -> None:
        self._entries: list[dict[str, Any]] = []
        self._exact: dict[str, dict[str, Any]] = {}
        self._normalized: dict[str, list[dict[str, Any]]] = {}
        self._compact: dict[str, list[dict[str, Any]]] = {}

        for item in classes:
            if not isinstance(item, dict):
                continue
            aliases = self._aliases_for_item(item)
            if not aliases:
                continue
            entry = {"item": item, "aliases": aliases}
            self._entries.append(entry)
            for alias in aliases:
                folded = alias.casefold().strip()
                if not folded:
                    continue
                self._exact.setdefault(folded, entry)
                normalized = self.normalize(alias)
                compact = self.compact(alias)
                if normalized:
                    self._normalized.setdefault(normalized, []).append(entry)
                if compact:
                    self._compact.setdefault(compact, []).append(entry)

    @staticmethod
    def strip_dynamic_suffix(value: str) -> str:
        return _HEX_SUFFIX_RE.sub("", value.strip()).strip(" _-")

    @staticmethod
    def strip_provider_suffix(value: str) -> str:
        return _PROVIDER_SUFFIX_RE.sub("", value.strip()).strip()

    @classmethod
    def normalize(cls, value: str) -> str:
        value = cls.strip_dynamic_suffix(value)
        value = cls.strip_provider_suffix(value)
        value = _CAMEL_RE.sub(" ", value)
        value = value.replace("+", " plus ")
        return " ".join(_NON_ALNUM_RE.sub(" ", value.casefold()).split())

    @classmethod
    def compact(cls, value: str) -> str:
        normalized = cls.normalize(value)
        return normalized.replace(" ", "")

    @staticmethod
    def _aliases_for_item(item: dict[str, Any]) -> set[str]:
        aliases: set[str] = set()
        for field in ("class_type", "display_name", "python_class"):
            value = str(item.get(field) or "").strip()
            if value:
                aliases.add(value)
        provider = str(item.get("provider") or "").strip()
        display = str(item.get("display_name") or "").strip()
        class_type = str(item.get("class_type") or "").strip()
        if provider:
            if display:
                aliases.add(f"{display} ({provider})")
            if class_type:
                aliases.add(f"{class_type} ({provider})")
        return aliases

    @staticmethod
    def _result(entry: dict[str, Any], workflow_name: str, matched_alias: str,
                reason: str, score: float) -> dict[str, Any]:
        return {
            "item": entry["item"],
            "workflow_name": workflow_name,
            "matched_alias": matched_alias,
            "reason": reason,
            "score": round(score, 4),
        }

    def resolve(self, workflow_name: str) -> dict[str, Any] | None:
        raw = workflow_name.strip()
        if not raw:
            return None

        exact = self._exact.get(raw.casefold())
        if exact:
            alias = next((a for a in exact["aliases"] if a.casefold() == raw.casefold()), raw)
            return self._result(exact, raw, alias, "exact", 1.0)

        stripped_hash = self.strip_dynamic_suffix(raw)
        if stripped_hash != raw:
            exact = self._exact.get(stripped_hash.casefold())
            if exact:
                return self._result(exact, raw, stripped_hash, "dynamic-hash", 0.99)

        stripped_provider = self.strip_provider_suffix(stripped_hash)
        if stripped_provider != stripped_hash:
            exact = self._exact.get(stripped_provider.casefold())
            if exact:
                return self._result(exact, raw, stripped_provider, "provider-suffix", 0.98)

        normalized = self.normalize(raw)
        normalized_entries = self._normalized.get(normalized, [])
        if len(normalized_entries) == 1:
            entry = normalized_entries[0]
            return self._result(entry, raw, normalized, "normalized", 0.96)

        compact = self.compact(raw)
        compact_entries = self._compact.get(compact, [])
        if len(compact_entries) == 1:
            entry = compact_entries[0]
            return self._result(entry, raw, compact, "compact", 0.94)

        best: tuple[float, dict[str, Any], str] | None = None
        for entry in self._entries:
            for alias in entry["aliases"]:
                alias_compact = self.compact(alias)
                if not alias_compact:
                    continue
                # Prefix matching is safe for generated node keys once the base
                # name is reasonably distinctive.
                if min(len(compact), len(alias_compact)) >= 8 and (
                    compact.startswith(alias_compact) or alias_compact.startswith(compact)
                ):
                    score = min(len(compact), len(alias_compact)) / max(len(compact), len(alias_compact))
                    score = max(score, 0.91)
                else:
                    score = SequenceMatcher(None, compact, alias_compact).ratio()
                if best is None or score > best[0]:
                    best = (score, entry, alias)

        if best and best[0] >= 0.90:
            return self._result(best[1], raw, best[2], "fuzzy", best[0])
        return None

    @classmethod
    def find_source_hint(cls, workflow_name: str, provider_paths: Iterable[Path]) -> dict[str, Any] | None:
        """Find a node label in source when mappings are built dynamically.

        The AST index intentionally does not execute custom-node modules. Some
        extensions build NODE_CLASS_MAPPINGS at runtime, so their labels may
        only appear as string literals or class names. For the small unresolved
        set, a bounded text scan provides a safe provider-level fallback.
        """
        raw = workflow_name.strip()
        bases = {
            raw,
            cls.strip_dynamic_suffix(raw),
            cls.strip_provider_suffix(cls.strip_dynamic_suffix(raw)),
        }
        bases = {value for value in bases if len(value) >= 4}
        normalized_target = cls.compact(raw)

        for provider_path in provider_paths:
            if not provider_path.is_dir():
                continue
            scanned = 0
            for file in provider_path.rglob("*"):
                if scanned >= 1500:
                    break
                if not file.is_file() or file.suffix.lower() not in {".py", ".js", ".ts", ".json"}:
                    continue
                if any(part.lower() in {"env", "venv", ".venv", "node_modules", ".git", "site-packages"} for part in file.parts):
                    continue
                try:
                    if file.stat().st_size > 2_000_000:
                        continue
                    text = file.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                scanned += 1
                if any(base in text for base in bases):
                    return {
                        "provider": provider_path.name,
                        "source_path": str(provider_path),
                        "source_file": str(file),
                        "class_type": raw,
                        "display_name": raw,
                        "python_class": cls.strip_provider_suffix(cls.strip_dynamic_suffix(raw)),
                        "alias_reason": "source-literal",
                        "alias_score": 0.88,
                    }
                # Filename/class-symbol fallback for labels whose punctuation or
                # spaces differ from the workflow representation.
                if normalized_target and normalized_target in cls.compact(file.stem):
                    return {
                        "provider": provider_path.name,
                        "source_path": str(provider_path),
                        "source_file": str(file),
                        "class_type": raw,
                        "display_name": raw,
                        "python_class": file.stem,
                        "alias_reason": "source-filename",
                        "alias_score": 0.84,
                    }
        return None
