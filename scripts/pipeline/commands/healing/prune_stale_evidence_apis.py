"""Prune fabricated/stale `evidence.apis` entries from content frontmatter.

Root-cause fix for G-39: attach_evidence.py merges newly-mined API tokens into
an existing evidence.apis list but never removes entries that don't (or no
longer) resolve against api_surface.json — e.g. a manually-curated evidence
entry citing a method that was later proven not to exist (see
StyleCollection.GetByName / GetByStyleIdentifier, seeded during S-72
evidence-repair for words/net before the scout preprocessor-exclusion fix).

This performs a line-level removal (not a full YAML re-parse/re-dump) so the
rest of the frontmatter — key order, quoting, blank lines — is left
byte-identical. Only exact `  - Token` bullet lines under an `apis:` key
inside an `evidence:` (or nested `sections[].`) block are candidates for
removal, and only when neither the full dotted token nor its class-name
prefix resolves against api_surface.json.

Usage:
    python scripts/pipeline/commands/healing/prune_stale_evidence_apis.py \
        {family} {platform} --files path1.md path2.md [--dry-run]
"""
import argparse
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PIPELINE_ROOT = _HERE.parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

_BULLET_RE = re.compile(r"^(\s*)-\s+(\S.*?)\s*$")
_APIS_KEY_RE = re.compile(r"^(\s*)apis:\s*$")


def load_known_api_tokens(api_surface_path: "Path | str") -> set:
    """Build the set of resolvable tokens: bare class names and Class.Member
    for every method, property, enum_member, and field in api_surface.json."""
    data = json.loads(Path(api_surface_path).read_text(encoding="utf-8"))
    classes = data.get("classes", data) if isinstance(data, dict) else data
    class_iter = classes.items() if isinstance(classes, dict) else (
        (c.get("name"), c) for c in classes
    )
    tokens = set()
    for cname, cdata in class_iter:
        if not cname:
            continue
        tokens.add(cname)
        for group in ("methods", "properties", "enum_members", "fields"):
            for m in (cdata.get(group) or []):
                mname = m.get("name") if isinstance(m, dict) else m
                if mname:
                    tokens.add(f"{cname}.{mname}")
    return tokens


def _resolves(token: str, known_tokens: set) -> bool:
    # A dotted token (Class.Member) must resolve as that EXACT qualified pair —
    # falling back to "the bare class exists" would silently accept any
    # fabricated member name on a real class (the actual bug this tool fixes).
    return token in known_tokens


def find_stale_api_lines(text: str, known_tokens: set) -> list:
    """Return 0-indexed line numbers of bullet entries under an `apis:` key
    whose token does not resolve against known_tokens."""
    lines = text.split("\n")
    stale = []
    in_apis_block = False
    apis_indent = None
    for i, line in enumerate(lines):
        m_key = _APIS_KEY_RE.match(line)
        if m_key:
            in_apis_block = True
            apis_indent = len(m_key.group(1))
            continue
        if in_apis_block:
            m_bullet = _BULLET_RE.match(line)
            if m_bullet and len(m_bullet.group(1)) >= apis_indent:
                token = m_bullet.group(2).strip().strip('"').strip("'")
                if not _resolves(token, known_tokens):
                    stale.append(i)
                continue
            # Any non-bullet, non-blank line at or below the key's indent ends the block.
            if line.strip() == "":
                continue
            in_apis_block = False
    return stale


def prune_file(filepath: "Path | str", known_tokens: set, dry_run: bool = False) -> dict:
    filepath = Path(filepath)
    text = filepath.read_text(encoding="utf-8")
    fm_end = text.find("\n---", 3) if text.startswith("---") else -1
    if fm_end == -1:
        return {"file": str(filepath), "removed": [], "status": "SKIP (no frontmatter)"}
    frontmatter = text[:fm_end + 1]
    rest = text[fm_end + 1:]

    stale_lines = find_stale_api_lines(frontmatter, known_tokens)
    if not stale_lines:
        return {"file": str(filepath), "removed": [], "status": "CLEAN"}

    fm_lines = frontmatter.split("\n")
    removed_tokens = [fm_lines[i].strip().lstrip("- ").strip() for i in stale_lines]
    new_fm_lines = [l for idx, l in enumerate(fm_lines) if idx not in set(stale_lines)]
    new_text = "\n".join(new_fm_lines) + rest

    if not dry_run:
        filepath.write_text(new_text, encoding="utf-8")

    return {
        "file": str(filepath),
        "removed": removed_tokens,
        "status": "WOULD_PRUNE" if dry_run else "PRUNED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--files", nargs="+", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_surface_path = _PIPELINE_ROOT.parent.parent / "knowledge" / args.family / args.platform / "merged" / "api_surface.json"
    if not api_surface_path.exists():
        # Fall back to repo-root-relative resolution when invoked from elsewhere.
        api_surface_path = Path("knowledge") / args.family / args.platform / "merged" / "api_surface.json"
    known_tokens = load_known_api_tokens(api_surface_path)

    results = [prune_file(f, known_tokens, dry_run=args.dry_run) for f in args.files]
    for r in results:
        print(f"{r['status']}: {r['file']}")
        for tok in r["removed"]:
            print(f"    - removed: {tok}")

    total_removed = sum(len(r["removed"]) for r in results)
    print(f"\nTotal stale evidence.apis entries {'that would be' if args.dry_run else ''} removed: {total_removed}")


if __name__ == "__main__":
    main()
