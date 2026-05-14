#!/usr/bin/env python3
"""Checkpoint store for standalone launch and migration workflows."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

DEFAULT_STATE_FILE = Path("reports") / "phase_state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_value(raw: str) -> Any:
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


def state_path(cli_path: str | None = None, env: dict[str, str] | None = None) -> Path:
    source_env = env if env is not None else os.environ
    if cli_path:
        return Path(cli_path)
    if source_env.get("PHASE_STATE_FILE"):
        return Path(source_env["PHASE_STATE_FILE"])
    return DEFAULT_STATE_FILE


def _backup_corrupt_state(path: Path) -> Path:
    backup = path.with_name(f"{path.stem}.corrupt-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}{path.suffix}")
    path.replace(backup)
    return backup


def _normalize_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {"values": {}, "updated_at": "", "updated_by": ""}
    values = record.get("values") if isinstance(record.get("values"), dict) else {}
    if not values and record.get("phase") not in (None, ""):
        values = {"phase": record["phase"]}
    return {
        "values": dict(values),
        "updated_at": str(record.get("updated_at", "")),
        "updated_by": str(record.get("updated_by", "")),
    }


def load_state(path: Path) -> tuple[dict[str, Any], Path | None]:
    if not path.exists():
        return {}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, _backup_corrupt_state(path)
    if not isinstance(data, dict):
        return {}, _backup_corrupt_state(path)
    return {key: _normalize_record(value) for key, value in data.items()}, None


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def product_key(family: str, platform: str) -> str:
    return f"{family}/{platform}"


def get_record(state: dict[str, Any], family: str, platform: str) -> dict[str, Any]:
    return _normalize_record(state.get(product_key(family, platform), {}))


def set_value(state: dict[str, Any], family: str, platform: str, key: str, value: Any, updated_by: str) -> dict[str, Any]:
    record = get_record(state, family, platform)
    record["values"][key] = value
    record["updated_at"] = _now_iso()
    record["updated_by"] = updated_by
    state[product_key(family, platform)] = record
    return record


def clear_value(state: dict[str, Any], family: str, platform: str, key: str | None = None) -> bool:
    pkey = product_key(family, platform)
    if pkey not in state:
        return False
    if key is None:
        del state[pkey]
        return True
    record = get_record(state, family, platform)
    if key not in record["values"]:
        return False
    del record["values"][key]
    record["updated_at"] = _now_iso()
    state[pkey] = record
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="get", choices=("get", "set", "clear"))
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("key", nargs="?")
    parser.add_argument("value", nargs="?")
    parser.add_argument("--state-file")
    parser.add_argument("--updated-by", default="agent")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    path = state_path(args.state_file)
    state, backup = load_state(path)
    if backup:
        print(f"WARN: corrupt state backed up to {backup}", file=sys.stderr)

    if args.command == "get":
        record = get_record(state, args.family, args.platform)
        value = record["values"].get(args.key) if args.key else None
        found = bool(record["values"]) if args.key is None else args.key in record["values"]
        payload = {"command": "get", "found": found, "key": args.key, "value": value, "record": record}
        print(json.dumps(payload, indent=2) if args.json else (f"{args.key}={value}" if found and args.key else json.dumps(record, indent=2) if found else "none"))
        return 0

    if args.command == "set":
        if not args.key:
            parser.error("set requires a key or phase value")
        key, raw = (args.key, args.value) if args.value is not None else ("phase", args.key)
        record = set_value(state, args.family, args.platform, key, _parse_value(raw), args.updated_by)
        save_state(path, state)
        payload = {"command": "set", "family": args.family, "platform": args.platform, "key": key, "value": record["values"][key], "changed": True}
        print(json.dumps(payload, indent=2) if args.json else f"stored {args.family}/{args.platform} {key}={record['values'][key]}")
        return 0

    changed = clear_value(state, args.family, args.platform, args.key)
    save_state(path, state)
    payload = {"command": "clear", "family": args.family, "platform": args.platform, "key": args.key, "changed": changed}
    print(json.dumps(payload, indent=2) if args.json else ("cleared" if changed else "not-found"))
    return 0 if changed else 1


if __name__ == "__main__":
    raise SystemExit(main())
