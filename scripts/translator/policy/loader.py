"""
ContentTypePolicy: loads translation rules for a given file path.
"""
from __future__ import annotations
import os
import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

_POLICY_DIR = Path(__file__).parent


@dataclass
class FieldPolicy:
    """Translation rules for frontmatter fields."""
    translate: list[str]
    translate_nested: list[str]
    preserve: list[str]
    translate_body: bool


@dataclass
class ContentTypePolicy:
    content_type: str  # products / docs / kb / reference / blog
    field_policy: FieldPolicy
    protected_patterns: list[dict]
    placeholder_format: str
    skip: bool = False

    @classmethod
    def for_path(cls, file_path: str) -> "ContentTypePolicy":
        """
        Detect content type from file path and return the appropriate policy.
        Raises ValueError if path cannot be mapped to a known content type.
        """
        fields_data = _load_yaml("fields.yaml")
        patterns_data = _load_yaml("patterns.yaml")

        path_str = str(file_path).replace("\\", "/")

        for ct_name, ct_data in fields_data["content_types"].items():
            if ct_data.get("skip"):
                continue
            pattern = ct_data.get("detect_pattern", "")
            if pattern and pattern in path_str:
                fm = ct_data.get("frontmatter", {})
                fp = FieldPolicy(
                    translate=fm.get("translate", []),
                    translate_nested=fm.get("translate_nested", []),
                    preserve=fm.get("preserve", []) + fields_data.get("universal_preserve", []),
                    translate_body=ct_data.get("translate_body", True),
                )
                return cls(
                    content_type=ct_name,
                    field_policy=fp,
                    protected_patterns=patterns_data.get("body_protected", []),
                    placeholder_format=patterns_data.get("placeholder_format", "⟦PH_{index:04d}⟧"),
                )

        raise ValueError(f"Cannot determine content type for path: {file_path}")

    def is_translatable_field(self, field_name: str) -> bool:
        """Check if a top-level frontmatter field should be translated."""
        if field_name in self.field_policy.preserve:
            return False
        return field_name in self.field_policy.translate


def _load_yaml(filename: str) -> dict:
    path = _POLICY_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
