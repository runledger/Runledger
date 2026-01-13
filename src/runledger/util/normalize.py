from __future__ import annotations

import re
from typing import Any

from runledger.config.models import NormalizationSpec, ReplaceTextSpec

_REMOVE = object()
_FLAG_MAP = {
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "s": re.DOTALL,
}


def merge_normalization(
    base: NormalizationSpec | None,
    override: NormalizationSpec | None,
) -> NormalizationSpec | None:
    if base is None:
        return override
    if override is None:
        return base
    return NormalizationSpec(
        strip_keys=base.strip_keys + override.strip_keys,
        strip_paths=base.strip_paths + override.strip_paths,
        replace_paths={**base.replace_paths, **override.replace_paths},
        replace_text=base.replace_text + override.replace_text,
    )


def normalize(value: Any, spec: NormalizationSpec | None) -> Any:
    if spec is None:
        return value
    result = value
    if spec.strip_keys:
        result = _strip_keys(result, set(spec.strip_keys))
    if spec.strip_paths:
        for path in spec.strip_paths:
            segments = _split_path(path)
            if not segments:
                continue
            result = _remove_path(result, segments)
            if result is _REMOVE:
                result = None
    if spec.replace_paths:
        for path, replacement in spec.replace_paths.items():
            segments = _split_path(path)
            if not segments:
                continue
            result = _replace_path(result, segments, replacement)
    if spec.replace_text:
        patterns = _compile_replace_text(spec.replace_text)
        result = _replace_text(result, patterns)
    return result


def _split_path(path: str) -> list[str]:
    return [segment for segment in path.split(".") if segment]


def _strip_keys(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_keys(item, keys)
            for key, item in value.items()
            if not (isinstance(key, str) and key in keys)
        }
    if isinstance(value, list):
        return [_strip_keys(item, keys) for item in value]
    return value


def _remove_path(value: Any, segments: list[str]) -> Any:
    if not segments:
        return _REMOVE
    segment = segments[0]
    rest = segments[1:]
    if isinstance(value, dict):
        updated: dict[str, Any] = {}
        for key, item in value.items():
            if segment == "*" or key == segment:
                replaced = _remove_path(item, rest)
                if replaced is _REMOVE:
                    continue
                updated[key] = replaced
            else:
                updated[key] = item
        return updated
    if isinstance(value, list):
        updated_list: list[Any] = []
        for index, item in enumerate(value):
            if segment == "*" or segment == str(index):
                replaced = _remove_path(item, rest)
                if replaced is _REMOVE:
                    continue
                updated_list.append(replaced)
            else:
                updated_list.append(item)
        return updated_list
    return value


def _replace_path(value: Any, segments: list[str], replacement: Any) -> Any:
    if not segments:
        return replacement
    segment = segments[0]
    rest = segments[1:]
    if isinstance(value, dict):
        updated: dict[str, Any] = {}
        for key, item in value.items():
            if segment == "*" or key == segment:
                updated[key] = _replace_path(item, rest, replacement)
            else:
                updated[key] = item
        return updated
    if isinstance(value, list):
        updated_list: list[Any] = []
        for index, item in enumerate(value):
            if segment == "*" or segment == str(index):
                updated_list.append(_replace_path(item, rest, replacement))
            else:
                updated_list.append(item)
        return updated_list
    return value


def _parse_flags(flags: str | None) -> int:
    if not flags:
        return 0
    value = 0
    for flag in flags.lower():
        value |= _FLAG_MAP.get(flag, 0)
    return value


def _compile_replace_text(specs: list[ReplaceTextSpec]) -> list[tuple[re.Pattern[str], str]]:
    compiled: list[tuple[re.Pattern[str], str]] = []
    for spec in specs:
        compiled.append((re.compile(spec.pattern, _parse_flags(spec.flags)), spec.replacement))
    return compiled


def _replace_text(value: Any, patterns: list[tuple[re.Pattern[str], str]]) -> Any:
    if isinstance(value, dict):
        return {key: _replace_text(item, patterns) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_text(item, patterns) for item in value]
    if isinstance(value, str):
        result = value
        for pattern, replacement in patterns:
            result = pattern.sub(replacement, result)
        return result
    return value
