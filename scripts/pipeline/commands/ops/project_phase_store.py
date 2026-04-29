"""Checkpoint store CLI for launch orchestration and legacy phase tracking."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile


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


def set_value(state: dict, family: str, platform: str, key: str, value, updated_by: str) -> dict:
    product_key = _product_key(family, platform)
    record = get_record(state, family, platform)
    record["values"][key] = value
    record["updated_at"] = _now_iso()
    record["updated_by"] = updated_by
    state[product_key] = record
    return record


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
    parser.add_argument("command", nargs="?", default="get", choices=("get", "set", "clear"))
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("key", nargs="?")
    parser.add_argument("value", nargs="?")
    parser.add_argument("--state-file", help="Override reports/phase_state.json")
    parser.add_argument("--updated-by", default="agent")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    state_path = _state_path(args.state_file)
    state, backup = load_state(state_path)
    if backup:
        print(f"WARN: Corrupt state backed up to {backup}", file=os.sys.stderr)

    if args.command == "get":
        record = get_record(state, args.family, args.platform)
        _emit_get(record, args.key, args.json)
        return 0

    if args.command == "set":
        if not args.key:
            parser.error("set requires at least one value")
        key = args.key
        raw_value = args.value
        if raw_value is None:
            key, raw_value = "phase", key
        record = set_value(state, args.family, args.platform, key, _parse_value(raw_value), args.updated_by)
        save_state(state_path, state)
        _emit_mutation("set", args.family, args.platform, key, record["values"][key], True, args.json)
        return 0

    changed = clear_value(state, args.family, args.platform, args.key)
    save_state(state_path, state)
    _emit_mutation("clear", args.family, args.platform, args.key, None, changed, args.json)
    return 0 if changed else 1


if __name__ == "__main__":
    raise SystemExit(main())
