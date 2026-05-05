"""Translation subsystem module entrypoint.

Supports:
- `python -m scripts.translator ...` from repo root
- `python -m translator ...` when a top-level translator package is installed
"""

try:
    from .cli import main
except ImportError:  # pragma: no cover - fallback for installed top-level package
    from translator.cli import main  # type: ignore[no-redef]


if __name__ == "__main__":
    main()
