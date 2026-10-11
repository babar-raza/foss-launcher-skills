"""External Signals Schema — advisory signals from external tools.

External signals are NEVER authoritative. They supplement source-extracted
facts but cannot override them. The advisory flag is always True.

Public API:
    ExternalSignal  — single advisory signal from an external tool
    SignalBatch     — collection of signals with serialization
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


EXTERNAL_SIGNALS_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class ExternalSignal:
    """Single advisory signal from an external tool."""
    signal_type: str      # readme_feature, doc_code_conflict, coverage_gap
    text: str
    source: str           # "skill_seekers", "manual", etc.
    source_file: str = ""
    confidence: float = 0.5
    advisory: bool = True  # ALWAYS True — never overrides source facts

    def __post_init__(self):
        if not self.advisory:
            object.__setattr__(self, "advisory", True)


@dataclass
class SignalBatch:
    """Collection of external signals with metadata."""
    schema_version: str = EXTERNAL_SIGNALS_SCHEMA_VERSION
    family: str = ""
    platform: str = ""
    source: str = ""
    signals: list[ExternalSignal] = field(default_factory=list)

    @property
    def signal_count(self) -> int:
        return len(self.signals)

    def add_signal(self, signal: ExternalSignal) -> None:
        self.signals.append(signal)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "family": self.family,
            "platform": self.platform,
            "source": self.source,
            "signal_count": self.signal_count,
            "signals": [asdict(s) for s in self.signals],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict) -> SignalBatch:
        signals = [ExternalSignal(**s) for s in data.get("signals", [])]
        return cls(
            schema_version=data.get("schema_version", EXTERNAL_SIGNALS_SCHEMA_VERSION),
            family=data.get("family", ""),
            platform=data.get("platform", ""),
            source=data.get("source", ""),
            signals=signals,
        )

    @classmethod
    def read(cls, path: Path) -> SignalBatch:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
