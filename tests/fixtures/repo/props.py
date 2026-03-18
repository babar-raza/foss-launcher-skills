"""Property getter/setter fixtures for scout.py testing."""


class StyledText:
    """A text element with a readable and writable name property."""

    def __init__(self, name: str = ""):
        self._name = name
        self._size = 12

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = value

    @property
    def size(self) -> int:
        return self._size

    def apply(self) -> None:
        pass
