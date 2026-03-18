"""Sample Document class — minimal fixture for scout.py integration tests."""

# Format constants
DOCX = "docx"
PDF = "pdf"
RTF = "rtf"


class Document:
    """Represents a Word processing document."""

    def __init__(self, path: str = ""):
        self._path = path

    def load(self, path: str) -> bool:
        """Load a document from the given file path.

        Args:
            path: Filesystem path to the document file.

        Returns:
            True on success, False on failure.
        """
        self._path = path
        return True

    def save(self, path: str) -> None:
        """Save the document to the given file path.

        Args:
            path: Filesystem path for the output file.
        """
        pass

    def convert(self, output_format: str, output_path: str) -> bool:
        """Convert the document to another format.

        Args:
            output_format: Target format (e.g. "pdf", "rtf").
            output_path: Path for the converted output file.

        Returns:
            True on success.
        """
        return True
