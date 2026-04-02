"""pre_write.py — Mandatory pre-write hook that blocks content writes failing the audit gate.

Wraps scripts/pipeline/audit.py and provides a single call point for all
content-writing skills.

Usage:
    python scripts/pre_write.py <path> [--knowledge-root <path>]

Exit codes:
    0  PASS — file passed audit
    1  FAIL — write BLOCKED (audit findings, forbidden path, or missing knowledge)
    2  ERROR — bad arguments or unexpected error

Output (stdout):
    PASS: content/docs.aspose.org/.../page.md — evidence verified
    FAIL: content/docs.aspose.org/.../page.md — knowledge model not found (...). Run S-34→S-35→S-31 ...
    FAIL: content/docs.aspose.org/.../page.md — 3 finding(s):
      [FAIL] frontmatter evidence: block absent
      [FAIL] unverified API token: SomeClass
    ERROR: path argument required
"""
import sys
from pathlib import Path

# Allow imports from scripts/ and scripts/pipeline/
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "pipeline"))

from config_loader import load_config
from ops_log import log_entry
from path_guard import check_path


def _import_audit_files():
    """Lazy import of audit_files to allow mocking in tests."""
    from audit import audit_files  # noqa: PLC0415
    return audit_files


def pre_write_check(
    target,
    *,
    knowledge_root=None,
    config=None,
):
    """Check whether target file is safe to write.

    Args:
        target: Path to the file being written (relative or absolute).
        knowledge_root: Override knowledge root path.
        config: Pre-loaded config dict; loaded from config.yaml if None.

    Returns:
        (exit_code, message) tuple where exit_code is 0 (PASS/WARN), 1 (FAIL),
        or 2 (ERROR).
    """
    target = Path(target)
    path_str = str(target)

    if config is None:
        config = load_config()

    # Step 1: path guard check
    verdict, reason = check_path(target, config=config)
    if verdict == "DENY":
        msg = f"FAIL: {path_str} — forbidden path: {reason}"
        _safe_log("pre-write", "FAIL", errors=[msg])
        return (1, msg)

    # Step 2: if file doesn't exist yet, skip audit (pre-write on new file)
    if not target.exists():
        msg = f"PASS: {path_str} — new file, skipping audit"
        _safe_log("pre-write", "PASS")
        return (0, msg)

    # Step 3: run audit
    try:
        audit_files = _import_audit_files()
        findings = audit_files([str(target)], check_snippets=False)
    except FileNotFoundError as exc:
        msg = (
            f"FAIL: {path_str} — knowledge model not found ({exc.filename}). "
            "Run S-34\u2192S-35\u2192S-31 to bootstrap knowledge before writing content."
        )
        _safe_log("pre-write", "FAIL", errors=[str(exc)])
        return (1, msg)
    except Exception as exc:
        msg = f"FAIL: {path_str} — audit error: {exc}"
        _safe_log("pre-write", "FAIL", errors=[str(exc)])
        return (1, msg)

    if not findings:
        msg = f"PASS: {path_str} — evidence verified"
        _safe_log("pre-write", "PASS")
        return (0, msg)

    # Has findings — show all of them so the operator can fix in one pass
    lines = [f"FAIL: {path_str} — {len(findings)} finding(s):"]
    for f in findings:
        level = getattr(f, "level", "FAIL")
        message = getattr(f, "message", str(f))
        lines.append(f"  [{level}] {message}")
    msg = "\n".join(lines)
    _safe_log("pre-write", "FAIL", errors=[lines[0]])
    return (1, msg)


def _safe_log(skill, status, errors=None):
    """Write ops log entry, ignoring any logging failures."""
    try:
        log_entry(skill, status, errors=errors or [])
    except Exception:
        pass


def main(argv=None):
    """CLI entry point. Returns exit code."""
    args = argv if argv is not None else sys.argv[1:]

    knowledge_root = None
    positional = []

    i = 0
    while i < len(args):
        if args[i] in ("--knowledge-root", "-k") and i + 1 < len(args):
            knowledge_root = Path(args[i + 1])
            i += 2
        elif args[i].startswith("--knowledge-root="):
            knowledge_root = Path(args[i].split("=", 1)[1])
            i += 1
        else:
            positional.append(args[i])
            i += 1

    if not positional:
        msg = "ERROR: path argument required"
        print(msg)
        _safe_log("pre-write", "ERROR", errors=[msg])
        return 2

    target = positional[0]
    exit_code, message = pre_write_check(target, knowledge_root=knowledge_root)
    print(message)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
