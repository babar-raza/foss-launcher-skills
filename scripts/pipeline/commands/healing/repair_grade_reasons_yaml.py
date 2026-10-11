"""repair_grade_reasons_yaml.py — Fix malformed grade_reasons frontmatter.

Batch-repairs content files where grade_reasons list items were written at
column 0 (unindented bare list items) instead of as a proper YAML sequence
under a `grade_reasons:` key.

Same corruption pattern fixed in commit 04a445a1a7 for blog posts.
Applies the same fix to docs, reference, kb, and any remaining blog files.

Detection: looks for `^- ` lines in the YAML frontmatter block that appear
AFTER the `graded_content_hash:` line. These are grade_reasons items that
were never properly nested under the `grade_reasons:` key.

Two corruption classes handled:
  1. No grade_reasons key; bare `- {text}` items after `graded_content_hash:`
     -> Insert `grade_reasons:` key + indent + quote each item
  2. grade_reasons key present with properly indented items; extra bare `- {text}`
     items appear after (outside the sequence)
     -> Move extra items under the existing grade_reasons: key

Usage:
    .venv/Scripts/python scripts/pipeline/commands/healing/repair_grade_reasons_yaml.py
    .venv/Scripts/python scripts/pipeline/commands/healing/repair_grade_reasons_yaml.py --dry-run
    .venv/Scripts/python scripts/pipeline/commands/healing/repair_grade_reasons_yaml.py --dirs content/docs.aspose.org content/reference.aspose.org
"""
import argparse
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]  # scripts/pipeline/commands/healing -> repo root


def _fix_frontmatter(raw_text: str) -> tuple[str, bool]:
    """Return (fixed_text, changed_bool).

    Only modifies lines AFTER `graded_content_hash:` that start with `^- `
    (bare list items that should be under grade_reasons:).
    """
    if not raw_text.startswith("---"):
        return raw_text, False

    # Find end of frontmatter block
    end_idx = raw_text.find("\n---", 3)
    if end_idx == -1:
        return raw_text, False

    fm_raw = raw_text[3:end_idx]   # YAML content between the two ---
    body = raw_text[end_idx:]       # \n--- + rest of file

    lines = fm_raw.split("\n")

    # Find the index of the graded_content_hash: line
    graded_hash_idx = None
    for idx, line in enumerate(lines):
        if re.match(r"^graded_content_hash:", line):
            graded_hash_idx = idx
            break

    if graded_hash_idx is None:
        # No graded_content_hash -> no grade_reasons corruption possible
        return raw_text, False

    # Check if there are any bare `^- ` lines AFTER graded_content_hash:
    after_hash = lines[graded_hash_idx + 1:]
    has_bare_items = any(re.match(r"^- ", l) for l in after_hash)
    if not has_bare_items:
        return raw_text, False

    # Rebuild the frontmatter, fixing bare list items after graded_content_hash
    new_lines = lines[:graded_hash_idx + 1]  # Keep everything up to and including graded_content_hash
    i = graded_hash_idx + 1
    changed = False

    while i < len(lines):
        line = lines[i]

        if re.match(r"^- ", line):
            # This bare list item needs to be nested under grade_reasons:
            # Check if the previous non-empty line establishes grade_reasons context
            in_grade_reasons = False
            for j in range(len(new_lines) - 1, -1, -1):
                prev = new_lines[j]
                if prev == "":
                    continue
                if prev.rstrip() == "grade_reasons:":
                    in_grade_reasons = True
                elif re.match(r"^  - ", prev):
                    in_grade_reasons = True
                break

            text = line[2:].strip()
            # Ensure the value is quoted (avoids YAML special char issues)
            if not ((text.startswith('"') and text.endswith('"')) or
                    (text.startswith("'") and text.endswith("'"))):
                # Escape any existing double quotes in text
                text = text.replace('"', '\\"')
                text = f'"{text}"'

            if in_grade_reasons:
                new_lines.append(f"  - {text}")
            else:
                # Collect all consecutive bare items then insert under new grade_reasons:
                bare_items = []
                k = i
                while k < len(lines) and re.match(r"^- ", lines[k]):
                    t = lines[k][2:].strip()
                    if not ((t.startswith('"') and t.endswith('"')) or
                            (t.startswith("'") and t.endswith("'"))):
                        t = t.replace('"', '\\"')
                        t = f'"{t}"'
                    bare_items.append(f"  - {t}")
                    k += 1
                new_lines.append("grade_reasons:")
                new_lines.extend(bare_items)
                i = k
                changed = True
                continue
            changed = True
        else:
            new_lines.append(line)

        i += 1

    if not changed:
        return raw_text, False

    fixed_fm = "\n".join(new_lines)
    return "---" + fixed_fm + body, True


def repair_file(path: Path, dry_run: bool = False) -> bool:
    """Repair one file. Return True if changed."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  ERROR reading {path}: {e}", file=sys.stderr)
        return False

    fixed, changed = _fix_frontmatter(text)
    if not changed:
        return False

    if not dry_run:
        try:
            path.write_text(fixed, encoding="utf-8")
        except Exception as e:
            print(f"  ERROR writing {path}: {e}", file=sys.stderr)
            return False

    return True


def find_affected(dirs: list[Path]) -> list[Path]:
    """Find .md files with bare grade_reasons items (after graded_content_hash:) in frontmatter."""
    results = []
    for d in dirs:
        for p in sorted(d.rglob("*.md")):
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            if not text.startswith("---"):
                continue
            end = text.find("\n---", 3)
            if end == -1:
                continue
            fm = text[3:end]
            lines = fm.split("\n")

            after_hash = False
            for line in lines:
                if re.match(r"^graded_content_hash:", line):
                    after_hash = True
                    continue
                if after_hash and re.match(r"^- ", line):
                    results.append(p)
                    break
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview only; no writes")
    parser.add_argument(
        "--dirs", nargs="+",
        default=[
            "content/docs.aspose.org",
            "content/reference.aspose.org",
            "content/kb.aspose.org",
            "content/blog.aspose.org",
        ],
        help="Directories to scan (relative to repo root)",
    )
    args = parser.parse_args()

    dirs = [_REPO_ROOT / d for d in args.dirs]
    print(f"Scanning {len(dirs)} dir(s) for malformed grade_reasons YAML...")
    files = find_affected(dirs)
    print(f"Found {len(files)} file(s) with bare grade_reasons items in frontmatter")

    if not files:
        print("Nothing to repair.")
        return

    repaired = 0
    errors = 0
    for f in files:
        changed = repair_file(f, dry_run=args.dry_run)
        rel = f.relative_to(_REPO_ROOT)
        if changed:
            prefix = "DRY-RUN" if args.dry_run else "REPAIRED"
            print(f"  {prefix}: {rel}")
            repaired += 1
        else:
            print(f"  ERROR (no change made): {rel}", file=sys.stderr)
            errors += 1

    action = "Would repair" if args.dry_run else "Repaired"
    print(f"\n{action} {repaired} file(s); errors: {errors}")


if __name__ == "__main__":
    main()
