"""Negative controls for atomic filesystem replacement."""
from pathlib import Path

import pytest

from core import fs


@pytest.mark.parametrize(
    ("writer", "replacement"),
    [
        (fs.atomic_write, "replacement"),
        (fs.atomic_write_bytes, b"replacement"),
    ],
)
def test_failed_replace_preserves_original_and_removes_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    writer,
    replacement,
):
    target = tmp_path / "state.bin"
    target.write_bytes(b"original")

    def deny_replace(_source: Path, _target: Path):
        raise PermissionError("locked")

    # T3-MOCK: simulates a locked-file OS error from Path.replace
    monkeypatch.setattr(Path, "replace", deny_replace)
    # T3-MOCK: skips real retry backoff sleep
    monkeypatch.setattr(fs.time, "sleep", lambda _seconds: None)

    with pytest.raises(PermissionError, match="locked"):
        writer(target, replacement)

    assert target.read_bytes() == b"original"
    assert not target.with_suffix(target.suffix + ".tmp").exists()
    assert not list(tmp_path.glob("*.bak-*"))
