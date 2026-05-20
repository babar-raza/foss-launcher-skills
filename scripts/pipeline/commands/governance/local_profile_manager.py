# Adapted from aspose.org
"""local_profile_manager.py — CLI for managing local governance profiles.

Usage:
  python local_profile_manager.py create --profile balanced-local --ttl-days 30
  python local_profile_manager.py show
  python local_profile_manager.py expire
  python local_profile_manager.py validate
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent  # governance/ -> commands/ -> pipeline/ -> scripts/ -> repo
_PROFILE_DIR = _REPO_ROOT / ".local"
_PROFILE_PATH = _PROFILE_DIR / "governance.json"
_SCHEMA_VERSION = 1

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_profile import validate_profile, is_ci  # noqa: E402


def cmd_create(args: argparse.Namespace) -> int:
    if is_ci():
        print("ERROR: Cannot create local profile in CI environment.", file=sys.stderr)
        return 1
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz=timezone.utc)
    profile = {
        "schema_version": _SCHEMA_VERSION,
        "profile": args.profile,
        "operator": args.operator or "local",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=args.ttl_days)).isoformat(),
        "relaxations": {
            "token_pretooluse_enabled": True,
        },
        "audit_log": "reports/local-governance/audit.log",
    }
    _PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(f"Profile created: {_PROFILE_PATH}")
    print(f"  Mode: {args.profile}")
    print(f"  Expires: {profile['expires_at']}")
    return 0


def cmd_show(_args: argparse.Namespace) -> int:
    if not _PROFILE_PATH.exists():
        print("No local profile found.")
        return 1
    data = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
    print(json.dumps(data, indent=2))
    valid = validate_profile(data)
    ci = is_ci()
    print(f"\nValid: {valid}")
    print(f"CI environment: {ci}")
    print(f"Effective mode: {'strict' if ci or not valid else data.get('profile', 'strict')}")
    return 0


def cmd_expire(_args: argparse.Namespace) -> int:
    if not _PROFILE_PATH.exists():
        print("No local profile found.")
        return 1
    data = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
    data["expires_at"] = (datetime.now(tz=timezone.utc) - timedelta(seconds=1)).isoformat()
    _PROFILE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("Profile expired.")
    return 0


def cmd_validate(_args: argparse.Namespace) -> int:
    if not _PROFILE_PATH.exists():
        print("No local profile found. Effective mode: strict")
        return 1
    data = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
    valid = validate_profile(data)
    ci = is_ci()
    if ci:
        print("CI environment detected. Effective mode: strict (profile ignored)")
        return 2
    if valid:
        print(f"Profile valid. Effective mode: {data.get('profile', 'strict')}")
        return 0
    print("Profile invalid or expired. Effective mode: strict")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Local governance profile manager")
    sub = parser.add_subparsers(dest="command")

    p_create = sub.add_parser("create", help="Create a local governance profile")
    p_create.add_argument("--profile", default="balanced-local", help="Profile mode")
    p_create.add_argument("--ttl-days", type=int, default=30, help="Days until expiry")
    p_create.add_argument("--operator", default=None, help="Operator name")

    sub.add_parser("show", help="Show current profile")
    sub.add_parser("expire", help="Expire current profile")
    sub.add_parser("validate", help="Validate current profile")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    handlers = {
        "create": cmd_create,
        "show": cmd_show,
        "expire": cmd_expire,
        "validate": cmd_validate,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
