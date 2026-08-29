"""Fixture module: Writer (exported), UnexportedType and free_function (not
in __all__ -- exercise the reachable=False path)."""


class Writer:
    """Writes documents to disk."""

    def write(self, doc) -> bool:
        """Write the document, returning True on success."""
        return True


class UnexportedType:
    """A syntactically public class that is NOT in aspose_core's __all__."""

    pass


def free_function(x: int) -> int:
    """A free function not re-exported via __all__."""
    return x
