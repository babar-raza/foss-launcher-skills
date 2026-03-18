"""Enum fixtures for scout.py testing."""

from enum import IntEnum


class Color(IntEnum):
    RED = 1
    GREEN = 2
    BLUE = 3


class FileFormat(IntEnum):
    DOCX = 1
    PDF = 2
    RTF = 3
    HTML = 4
