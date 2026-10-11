"""Classify legacy refresh decisions against explicit Git intervals.

This command is forensic-only. It never mutates content and never promotes a
legacy decision into trusted run evidence. In particular,
``CURRENT_CONTENT_DEFECT`` requires an explicit truth-audit evidence map.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from commands.content.audit_content_hash import (  # noqa: E402
    _body_hash,
    _split_frontmatter_body,
)
from core.fs import atomic_write  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]
CLASSIFICATIONS = frozenset(
    {
        "WRONG_BASE_WINDOW",
        "LEGACY_UNBOUND",
        "SCHEMA_STAMP_ONLY",
        "REAL_BODY_CHANGE",
        "FRONTMATTER_ONLY",
        "REVERTED_SINCE_RUN",
        "CURRENT_CONTENT_DEFECT",
        "UNKNOWN",
    }
)


class ForensicError(RuntimeError):
    pass


def _resolve_commit(ref: str) -> str:
    if not ref or ref.startswith("-"):
        raise ForensicError(f"unsafe or empty Git ref: {ref!r}")
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ForensicError(
            f"unresolved Git ref {ref!r}: {(result.stderr or result.stdout).strip()}"
        )
    return result.stdout.strip()


def _safe_page_path(value: str) -> str:
    path = Path(value)
    if (
        not isinstance(value, str)
        or not value
        or path.is_absolute()
        or ".." in path.parts
        or not path.as_posix().startswith("content/")
    ):
        raise ForensicError(f"unsafe decision page path: {value!r}")
    return path.as_posix()


def _repo_relative(path: Path, label: str) -> str:
    candidate = path if path.is_absolute() else REPO_ROOT / path
    try:
        return candidate.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ForensicError(f"{label} must be inside the repository: {path}") from exc


def _git_text(commit: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        return None
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _git_texts(commit: str, paths: list[str]) -> dict[str, str | None]:
    """Read many blobs through one git cat-file process."""
    specs = [f"{commit}:{path}" for path in paths]
    result = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=REPO_ROOT,
        input=("\n".join(specs) + "\n").encode("utf-8"),
        capture_output=True,
        timeout=max(30, len(paths) // 4),
    )
    if result.returncode != 0:
        raise ForensicError(
            f"git cat-file failed for {commit}: {result.stderr.decode(errors='replace')}"
        )
    output = result.stdout
    offset = 0
    loaded: dict[str, str | None] = {}
    for path, spec in zip(paths, specs):
        newline = output.find(b"\n", offset)
        if newline < 0:
            raise ForensicError(f"truncated git cat-file output for {spec}")
        header = output[offset:newline].decode("utf-8", errors="replace")
        offset = newline + 1
        if header.endswith(" missing"):
            loaded[path] = None
            continue
        parts = header.rsplit(" ", 2)
        if len(parts) != 3 or parts[1] != "blob":
            raise ForensicError(f"unexpected git cat-file header: {header}")
        size = int(parts[2])
        raw = output[offset:offset + size]
        offset += size + 1  # blob bytes plus protocol newline
        try:
            loaded[path] = raw.decode("utf-8")
        except UnicodeDecodeError:
            loaded[path] = None
    return loaded


def _frontmatter_hash(text: str | None) -> str | None:
    if text is None:
        return None
    frontmatter, _ = _split_frontmatter_body(text)
    return "sha256:" + hashlib.sha256(frontmatter.encode("utf-8")).hexdigest()


def _normalized_body_hash(text: str | None) -> str | None:
    return None if text is None else "sha256:" + _body_hash(text)


def classify_row(
    row: dict,
    *,
    base_text: str | None,
    end_text: str | None,
    current_text: str | None,
    claimed_base_text: str | None = None,
    truth_defect: dict | None = None,
) -> tuple[str, dict]:
    """Classify one row without treating ledger intent as content truth."""
    hashes = {
        "body_before": _normalized_body_hash(base_text),
        "body_at_run_end": _normalized_body_hash(end_text),
        "body_current": _normalized_body_hash(current_text),
        "body_at_claimed_base": _normalized_body_hash(claimed_base_text),
        "frontmatter_before": _frontmatter_hash(base_text),
        "frontmatter_at_run_end": _frontmatter_hash(end_text),
        "frontmatter_current": _frontmatter_hash(current_text),
    }

    if truth_defect and truth_defect.get("verdict") == "CURRENT_CONTENT_DEFECT":
        if not truth_defect.get("evidence_refs"):
            return "UNKNOWN", {**hashes, "reason": "truth defect lacks evidence_refs"}
        return "CURRENT_CONTENT_DEFECT", {
            **hashes,
            "reason": "separate current truth audit proves a defect",
            "truth_evidence_refs": truth_defect["evidence_refs"],
        }

    if (
        base_text is not None
        and end_text is not None
        and claimed_base_text is not None
        and hashes["body_before"] != hashes["body_at_run_end"]
        and hashes["body_at_claimed_base"] == hashes["body_at_run_end"]
    ):
        return "WRONG_BASE_WINDOW", {
            **hashes,
            "reason": "claimed base is inside the real body-change interval",
        }

    if (
        base_text is not None
        and end_text is not None
        and current_text is not None
        and hashes["body_before"] != hashes["body_at_run_end"]
        and hashes["body_current"] == hashes["body_before"]
    ):
        return "REVERTED_SINCE_RUN", {
            **hashes,
            "reason": "run-end body changed but current body returned to the base hash",
        }

    if end_text is not None and (
        base_text is None or hashes["body_before"] != hashes["body_at_run_end"]
    ):
        return "REAL_BODY_CHANGE", {
            **hashes,
            "reason": (
                "page was generated in the interval"
                if base_text is None
                else "normalized body differs across the explicit interval"
            ),
        }

    if (
        base_text is not None
        and end_text is not None
        and hashes["frontmatter_before"] != hashes["frontmatter_at_run_end"]
    ):
        return "FRONTMATTER_ONLY", {
            **hashes,
            "reason": "body is stable and frontmatter differs across the interval",
        }

    has_run_identity = bool(row.get("run_id"))
    has_hash_pair = bool(
        row.get("body_hash_before") and row.get("body_hash_after")
    )
    if row.get("schema_stamp_only") is True:
        return "SCHEMA_STAMP_ONLY", {
            **hashes,
            "reason": "row explicitly records metadata-only schema migration",
        }
    if not has_run_identity or not has_hash_pair:
        return "LEGACY_UNBOUND", {
            **hashes,
            "reason": "decision lacks trustworthy run identity or before/after hashes",
        }
    return "UNKNOWN", {
        **hashes,
        "reason": "available Git and ledger evidence does not prove a disposition",
    }


def _load_legacy_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("pages"), dict):
        raise ForensicError("legacy decision input must contain a pages object")
    rows = []
    for page_path, entry in data["pages"].items():
        if not isinstance(entry, dict) or entry.get("decision") != "BODY_UPDATED":
            continue
        rows.append({"page_path": _safe_page_path(page_path), **entry})
    return rows


def run_forensics(
    family: str,
    platform: str,
    *,
    base: str,
    end: str,
    claimed_base: str | None = None,
    current: str = "HEAD",
    decisions: Path | None = None,
    truth_evidence: Path | None = None,
    output: Path | None = None,
    text_loader: Callable[[str, str], str | None] = _git_text,
) -> dict:
    base_sha = _resolve_commit(base)
    end_sha = _resolve_commit(end)
    current_sha = _resolve_commit(current)
    claimed_sha = _resolve_commit(claimed_base) if claimed_base else None
    decision_path = decisions or (
        REPO_ROOT
        / "reports"
        / "refresh_review"
        / family
        / platform
        / "page_decisions.json"
    )
    decision_path = REPO_ROOT / _repo_relative(decision_path, "decision input")
    rows = _load_legacy_rows(decision_path)
    page_paths = [row["page_path"] for row in rows]
    truth_map: dict = {}
    if truth_evidence:
        truth_map = json.loads(truth_evidence.read_text(encoding="utf-8"))
        if not isinstance(truth_map, dict):
            raise ForensicError("truth evidence must be an object keyed by page path")

    if text_loader is _git_text:
        base_texts = _git_texts(base_sha, page_paths)
        end_texts = _git_texts(end_sha, page_paths)
        current_texts = _git_texts(current_sha, page_paths)
        claimed_texts = (
            _git_texts(claimed_sha, page_paths) if claimed_sha else {}
        )
    else:
        base_texts = {path: text_loader(base_sha, path) for path in page_paths}
        end_texts = {path: text_loader(end_sha, path) for path in page_paths}
        current_texts = {
            path: text_loader(current_sha, path) for path in page_paths
        }
        claimed_texts = (
            {path: text_loader(claimed_sha, path) for path in page_paths}
            if claimed_sha
            else {}
        )

    classified = []
    for row in rows:
        path = row["page_path"]
        disposition, evidence = classify_row(
            row,
            base_text=base_texts[path],
            end_text=end_texts[path],
            current_text=current_texts[path],
            claimed_base_text=claimed_texts.get(path),
            truth_defect=truth_map.get(path),
        )
        if disposition not in CLASSIFICATIONS:
            raise AssertionError(disposition)
        classified.append(
            {
                "page_path": path,
                "legacy_decision": row.get("decision"),
                "classification": disposition,
                **evidence,
            }
        )

    counts = Counter(row["classification"] for row in classified)
    report = {
        "schema_version": 1,
        "family": family,
        "platform": platform,
        "forensic_only": True,
        "legacy_unbound_input": True,
        "decision_source": decision_path.relative_to(REPO_ROOT).as_posix(),
        "base_commit_sha": base_sha,
        "claimed_base_commit_sha": claimed_sha,
        "run_end_commit_sha": end_sha,
        "current_commit_sha": current_sha,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "total_flagged_rows": len(classified),
        "classification_counts": dict(sorted(counts.items())),
        "reconciled": sum(counts.values()) == len(classified),
        "current_content_defects": counts.get("CURRENT_CONTENT_DEFECT", 0),
        "rows": classified,
    }
    output_path = output or (
        REPO_ROOT
        / "reports"
        / "refresh_forensics"
        / family
        / platform
        / f"{base_sha[:12]}-{end_sha[:12]}.json"
    )
    output_path = REPO_ROOT / _repo_relative(output_path, "forensic output")
    atomic_write(
        output_path,
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
    )
    report["output_path"] = output_path.relative_to(REPO_ROOT).as_posix()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify legacy refresh rows against explicit Git intervals"
    )
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--base", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--claimed-base")
    parser.add_argument("--current", default="HEAD")
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--truth-evidence", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_forensics(
            args.family,
            args.platform,
            base=args.base,
            end=args.end,
            claimed_base=args.claimed_base,
            current=args.current,
            decisions=args.decisions,
            truth_evidence=args.truth_evidence,
            output=args.output,
        )
    except (ForensicError, OSError, json.JSONDecodeError) as exc:
        print(f"FORENSICS UNKNOWN: {exc}", file=sys.stderr)
        return 3
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    return 0 if report["reconciled"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
