"""
Frontmatter field walker and setter.
Yields (path_str, value) for each translatable field.
Supports nested paths like "content[0].title_left".
"""
from __future__ import annotations
import re
from typing import Iterator, Any


_ARRAY_INDEX_RE = re.compile(r'^([^[]+)\[(\d+|\*)\]$')


def iter_translatable_fields(
    frontmatter: dict,
    translate_fields: list[str],
    nested_paths: list[str],
) -> Iterator[tuple[str, str]]:
    """
    Yield (resolved_path, value) for each translatable string field.

    translate_fields: top-level field names to translate
    nested_paths: dot-notation paths, e.g. "content[*].title_left"
    """
    # Top-level fields
    for field_name in translate_fields:
        if field_name in frontmatter:
            val = frontmatter[field_name]
            if isinstance(val, str) and val.strip():
                yield (field_name, val)
            elif isinstance(val, list):
                # e.g. keywords: [python, pdf]
                for i, item in enumerate(val):
                    if isinstance(item, str) and item.strip():
                        yield (f"{field_name}[{i}]", item)

    # Nested paths
    for path_pattern in nested_paths:
        yield from _resolve_nested(frontmatter, path_pattern, "")


def _resolve_nested(
    data: Any,
    path_pattern: str,
    resolved_prefix: str,
) -> Iterator[tuple[str, str]]:
    """
    Recursively resolve a dot-notation path pattern against data.
    Handles [*] wildcards by iterating all array elements.
    """
    if not path_pattern:
        if isinstance(data, str) and data.strip():
            yield (resolved_prefix, data)
        return

    parts = path_pattern.split(".", 1)
    current = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    # Check for array index
    m = _ARRAY_INDEX_RE.match(current)
    if m:
        key, idx = m.group(1), m.group(2)
        if not isinstance(data, dict) or key not in data:
            return
        array = data[key]
        if not isinstance(array, list):
            return

        if idx == "*":
            for i, item in enumerate(array):
                prefix = f"{resolved_prefix}.{key}[{i}]" if resolved_prefix else f"{key}[{i}]"
                yield from _resolve_nested(item, rest, prefix)
        else:
            i = int(idx)
            if i < len(array):
                prefix = f"{resolved_prefix}.{key}[{i}]" if resolved_prefix else f"{key}[{i}]"
                yield from _resolve_nested(array[i], rest, prefix)
    else:
        # Regular key
        if not isinstance(data, dict) or current not in data:
            return
        prefix = f"{resolved_prefix}.{current}" if resolved_prefix else current
        yield from _resolve_nested(data[current], rest, prefix)


def set_field(frontmatter: dict, path: str, value: str) -> None:
    """
    Set a value at a dot-notation path in the frontmatter dict.
    Supports indexed paths like "content[0].title_left".
    Modifies frontmatter in-place.
    """
    parts = path.split(".", 1)
    current = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    m = _ARRAY_INDEX_RE.match(current)
    if m:
        key, idx = m.group(1), m.group(2)
        array = frontmatter.get(key, [])
        i = int(idx)
        if rest:
            set_field(array[i], rest, value)
        else:
            array[i] = value
    else:
        if rest:
            set_field(frontmatter[current], rest, value)
        else:
            frontmatter[current] = value
