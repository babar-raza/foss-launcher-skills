"""Dataclass fixtures for scout.py testing."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PageSettings:
    width: float
    height: float
    margin: float = 1.0
    orientation: str = "portrait"


@dataclass
class Metadata:
    title: str
    author: Optional[str] = None
    _internal: str = ""
