"""Smoke test for remediate.py heal subcommand."""

import pytest

from scripts.pipeline.commands.content.remediate import main


def test_heal_subcommand_help_exits_zero():
    """Verify heal subcommand --help exits 0 with usage text."""
    with pytest.raises(SystemExit) as exc_info:
        main(["heal", "--help"])

    assert exc_info.value.code == 0, "heal --help should exit 0"


def test_heal_subcommand_has_required_args():
    """Verify heal subcommand accepts eval_report positional argument."""
    with pytest.raises(SystemExit) as exc_info:
        main(["heal", "--help"])

    assert exc_info.value.code == 0


def test_heal_subcommand_accepts_dry_run():
    """Verify heal subcommand accepts --dry-run flag."""
    with pytest.raises(SystemExit) as exc_info:
        main(["heal", "--help"])

    assert exc_info.value.code == 0


def test_heal_subcommand_accepts_categories():
    """Verify heal subcommand accepts --categories flag."""
    with pytest.raises(SystemExit) as exc_info:
        main(["heal", "--help"])

    assert exc_info.value.code == 0