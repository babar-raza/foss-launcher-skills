"""Checkpoint store CLI for launch orchestration and legacy phase tracking.

HARDEN-A2 (2026-07-22): every mutation runs under an advisory FileLock — the
previous read-mutate-save had no lock, so two concurrent CLI invocations could
silently drop one another's checkpoint writes (lost update).

HARDEN-A5 (2026-07-22): a checkpoint may carry an artifact fingerprint —
`set ... --artifact <path>` records sha256+size for each named artifact next to
the boolean (as `{key}__fingerprint`), and `verify` recomputes them so a resume
can detect a checkpoint whose underlying artifact was corrupted/reverted since
it was certified. Bool-only legacy entries verify as "unverifiable" (warn,
never block) — no flag day.

HARDEN-A6 (2026-07-28, MT012): `set <family> <platform> blog_done true` with no
`--artifact` is refused outright — found live as cells/cpp's phase_state.json
entry carrying `blog_done: true` with zero blog content anywhere on disk
(content/blog.aspose.org/cells/ has no cpp/ subdirectory), predating HARDEN-A5's
fingerprint mechanism and never re-verified since. A blog stage that is
legitimately skipped (e.g. below the site-planner's blog-eligibility threshold)
should record `blog_skipped <reason>` instead — an ordinary key/value pair, no
special handling needed. Scoped to `blog_done` only (the confirmed live
instance of this lie), not generalized to every `_done` key.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from advisory_lock import FileLock  # noqa: E402


DEFAULT_STATE_FILE = Path("reports") / "phase_state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_value(raw: str):
    lowered = raw.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _state_path(cli_path: str | None) -> Path:
    env_path = os.environ.get("PHASE_STATE_FILE")
    if cli_path:
        return Path(cli_path)
    if env_path:
        return Path(env_path)
    return DEFAULT_STATE_FILE


def _backup_corrupt_state(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.stem}.corrupt-{stamp}{path.suffix}")
    path.replace(backup)
    return backup


def _normalize_record(record) -> dict:
    if not isinstance(record, dict):
        return {"values": {}, "updated_at": "", "updated_by": ""}

    if "values" in record and isinstance(record["values"], dict):
        values = dict(record["values"])
    else:
        values = {}
        phase = record.get("phase")
        if phase not in (None, ""):
            values["phase"] = phase

    return {
        "values": values,
        "updated_at": record.get("updated_at", ""),
        "updated_by": record.get("updated_by", ""),
    }


def load_state(path: Path) -> tuple[dict, Path | None]:
    if not path.exists():
        return {}, None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, _backup_corrupt_state(path)

    if not isinstance(data, dict):
        return {}, _backup_corrupt_state(path)

    normalized = {key: _normalize_record(value) for key, value in data.items()}
    return normalized, None


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _product_key(family: str, platform: str) -> str:
    return f"{family}/{platform}"


def get_record(state: dict, family: str, platform: str) -> dict:
    return _normalize_record(state.get(_product_key(family, platform), {}))


def validate_completion(state: dict, family: str, platform: str) -> list[str]:
    """Check for inconsistencies in a product's phase state.

    Returns a list of warning strings (empty if consistent).
    """
    warnings: list[str] = []
    record = get_record(state, family, platform)
    vals = record.get("values", {})

    if vals.get("readiness_done"):
        hgate_dir = Path("reports") / "human-review"
        slug = f"{family}-{platform}"
        for gate in ("h01", "h02", "h03", "h04", "h05"):
            gate_file = hgate_dir / f"{slug}-{gate}-sample.md"
            if not gate_file.is_file():
                warnings.append(
                    f"readiness_done=true but H-gate file missing: {gate_file.name}"
                )
    return warnings


def _fingerprint_artifacts(artifact_paths: list[str]) -> dict:
    """Compute the HARDEN-A5 fingerprint block for a checkpoint's artifacts."""
    artifacts = []
    for raw in artifact_paths:
        p = Path(raw)
        entry: dict = {"path": raw.replace("\\", "/")}
        try:
            data = p.read_bytes()
            entry["sha256"] = hashlib.sha256(data).hexdigest()
            entry["size"] = len(data)
        except OSError as exc:
            entry["error"] = f"unreadable at set time: {exc}"
        artifacts.append(entry)
    return {"verified_at": _now_iso(), "artifacts": artifacts}


def set_value(
    state: dict,
    family: str,
    platform: str,
    key: str,
    value,
    updated_by: str,
    artifact_paths: list[str] | None = None,
) -> dict:
    product_key = _product_key(family, platform)
    record = get_record(state, family, platform)
    record["values"][key] = value
    if artifact_paths:
        record["values"][f"{key}__fingerprint"] = _fingerprint_artifacts(artifact_paths)
    record["updated_at"] = _now_iso()
    record["updated_by"] = updated_by
    state[product_key] = record
    return record


def verify_checkpoint(
    state: dict, family: str, platform: str, key: str
) -> tuple[bool, list[str]]:
    """Re-verify a checkpoint against its recorded artifact fingerprint (A5).

    Returns (ok, notes). ok=False only on a REAL mismatch (artifact missing,
    unreadable, or content changed since the checkpoint was certified).
    A true checkpoint with no fingerprint is (True, ["unverifiable: ..."]) —
    legacy bool-only entries warn but never block.
    """
    record = get_record(state, family, platform)
    vals = record.get("values", {})
    if not vals.get(key):
        return False, [f"checkpoint {key} is not set (or falsy)"]

    fingerprint = vals.get(f"{key}__fingerprint")
    if not isinstance(fingerprint, dict) or not fingerprint.get("artifacts"):
        return True, [f"unverifiable: no fingerprint recorded for {key} (legacy entry)"]

    problems: list[str] = []
    for entry in fingerprint["artifacts"]:
        raw = entry.get("path", "")
        p = Path(raw)
        if entry.get("error"):
            problems.append(f"{raw}: was unreadable when fingerprinted ({entry['error']})")
            continue
        try:
            data = p.read_bytes()
        except OSError:
            problems.append(f"{raw}: artifact missing/unreadable (was present at set time)")
            continue
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != entry.get("sha256"):
            problems.append(
                f"{raw}: content changed since checkpoint "
                f"(sha256 {entry.get('sha256', '?')[:12]}... -> {actual_sha[:12]}...)"
            )
    return (not problems), problems


def clear_value(state: dict, family: str, platform: str, key: str | None) -> bool:
    product_key = _product_key(family, platform)
    if product_key not in state:
        return False

    if key is None:
        del state[product_key]
        return True

    record = get_record(state, family, platform)
    if key not in record["values"]:
        return False

    del record["values"][key]
    record["updated_at"] = _now_iso()
    state[product_key] = record
    return True


def _emit_get(record: dict, key: str | None, as_json: bool) -> None:
    found = bool(record["values"]) if key is None else key in record["values"]
    payload = {
        "command": "get",
        "found": found,
        "key": key,
        "value": record["values"].get(key) if key else None,
        "record": record,
    }
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if not found:
        print("none")
        return

    if key:
        print(f"{key}={record['values'][key]}")
        return

    print(json.dumps(record, indent=2, ensure_ascii=False))


def _emit_mutation(command: str, family: str, platform: str, key: str | None, value, changed: bool, as_json: bool) -> None:
    payload = {
        "command": command,
        "family": family,
        "platform": platform,
        "key": key,
        "value": value,
        "changed": changed,
    }
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    suffix = f" {key}" if key else ""
    if command == "set":
        print(f"stored {family}/{platform} {key}={value}")
    else:
        status = "cleared" if changed else "not-found"
        print(f"{status} {family}/{platform}{suffix}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="project_phase_store",
        description="Checkpoint store for launch orchestration and legacy phase tracking.",
    )
    parser.add_argument("command", nargs="?", default="get",
                        choices=("get", "set", "clear", "verify"))
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("key", nargs="?")
    parser.add_argument("value", nargs="?")
    parser.add_argument("--state-file", help="Override reports/phase_state.json")
    parser.add_argument("--updated-by", default="agent")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--artifact", action="append", default=None, dest="artifacts",
                        help="(set only, repeatable) artifact path this checkpoint certifies; "
                             "records a sha256 fingerprint verified later by 'verify' (HARDEN-A5)")
    args = parser.parse_args(argv)

    state_path = _state_path(args.state_file)

    if args.command == "get":
        state, backup = load_state(state_path)
        if backup:
            print(f"WARN: Corrupt state backed up to {backup}", file=sys.stderr)
        record = get_record(state, args.family, args.platform)
        _emit_get(record, args.key, args.json)
        return 0

    if args.command == "verify":
        if not args.key:
            parser.error("verify requires a key")
        state, backup = load_state(state_path)
        if backup:
            print(f"WARN: Corrupt state backed up to {backup}", file=sys.stderr)
        ok, notes = verify_checkpoint(state, args.family, args.platform, args.key)
        payload = {"command": "verify", "family": args.family, "platform": args.platform,
                   "key": args.key, "ok": ok, "notes": notes}
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"{'OK' if ok else 'FAIL'}: {args.family}/{args.platform} {args.key}")
            for note in notes:
                print(f"  {note}")
        return 0 if ok else 1

    # Mutations run entirely under the state-file lock (HARDEN-A2): the
    # unlocked read-mutate-save here was a real lost-update race between
    # concurrent sessions.
    with FileLock(str(state_path) + ".lock", timeout=10.0):
        state, backup = load_state(state_path)
        if backup:
            print(f"WARN: Corrupt state backed up to {backup}", file=sys.stderr)

        if args.command == "set":
            if not args.key:
                parser.error("set requires at least one value")
            key = args.key
            raw_value = args.value
            if raw_value is None:
                key, raw_value = "phase", key
            parsed_value = _parse_value(raw_value)
            if key == "blog_done" and parsed_value and not args.artifacts:
                parser.error(
                    "set blog_done=true requires --artifact <path> (repeatable) "
                    "proving real blog content exists on disk. If the blog stage "
                    "was legitimately skipped, record that instead: "
                    "set <family> <platform> blog_skipped \"<reason>\" (HARDEN-A6)"
                )
            record = set_value(state, args.family, args.platform, key,
                               parsed_value, args.updated_by,
                               artifact_paths=args.artifacts)
            save_state(state_path, state)
            _emit_mutation("set", args.family, args.platform, key, record["values"][key], True, args.json)
            for w in validate_completion(state, args.family, args.platform):
                print(f"WARN: {w}", file=sys.stderr)
            return 0

        changed = clear_value(state, args.family, args.platform, args.key)
        save_state(state_path, state)
    _emit_mutation("clear", args.family, args.platform, args.key, None, changed, args.json)
    return 0 if changed else 1


if __name__ == "__main__":
    raise SystemExit(main())
