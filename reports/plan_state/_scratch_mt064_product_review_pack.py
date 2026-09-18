"""One-off review-pack builder for SEO-PER-PRODUCT-COMMIT-REVIEW.
Scratch script under reports/plan_state/ (gitignored, tier-1 writable).

Automates the v14 "Per-Product Human Commit Review Gate" procedure's steps
1-4: real commit history for THIS MISSION's own SEO work touching a family
(scoped by the established "(seo)" commit-message convention every real
SEO commit in this repo's history uses -- git_plumb_commit.py's --skills/
--plan flow always produces a conventional-commit type(seo): subject line;
this is NOT a path-only git log, since the raw content/keywords path glob
alone pulls in thousands of unrelated commits from every other mission that
has ever touched that family's content, which is not what "this mission's
real commit history" means), a scope-honesty check per commit (the REAL,
whole-commit file list vs. the declared family -- exactly the check that
caught Finding #54's 3d/java contamination), a current keyword-count
snapshot by platform, and real content/*.md diffs for any in-scope commit.

Usage: PY _scratch_mt064_product_review_pack.py <family> <out.json>
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def run(args):
    return subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _seo_commits_touching(pathspec: str) -> list[dict]:
    log = run(["git", "log", "--format=%H\t%ad\t%s", "--date=short", "-i", "--grep=(seo)", "--", pathspec])
    commits = []
    for line in log.stdout.splitlines():
        if not line.strip():
            continue
        sha, date, subject = line.split("\t", 2)
        commits.append({"sha": sha, "date": date, "subject": subject})
    return commits


def build_pack(family: str) -> dict:
    kw_commits = _seo_commits_touching(f"keywords/{family}.json")
    content_commits = _seo_commits_touching(f"content/*/en/{family}/**")
    by_sha = {c["sha"]: c for c in kw_commits + content_commits}
    commits = sorted(by_sha.values(), key=lambda c: c["date"])

    family_content_re = re.compile(rf"^content/[^/]+(/en)?/{re.escape(family)}/")
    keywords_path = f"keywords/{family}.json"
    other_family_keywords_touches = []  # informational: expected for a disclosed multi-family batch
    content_prose_anomalies = []  # real flag: this mission's writable surface is never body prose
    content_md_touches = []

    for c in commits:
        r = run(["git", "show", "--name-only", "--format=", c["sha"]])
        files = [f for f in r.stdout.splitlines() if f.strip()]
        for f in files:
            in_scope = (f == keywords_path) or bool(family_content_re.match(f))
            if in_scope:
                if f.endswith(".md") and family_content_re.match(f):
                    content_md_touches.append({"sha": c["sha"], "path": f})
                continue
            if f.startswith("keywords/") and f.endswith(".json"):
                other_family_keywords_touches.append({"sha": c["sha"], "subject": c["subject"], "file": f})
            elif f.startswith("content/") and f.endswith(".md"):
                # A different family's real body prose touched by a commit
                # claiming to be about THIS family's keyword quarantine/
                # generation work -- this is exactly Finding #54's shape and
                # gets its own flag, never silently folded into the generic
                # "keywords json batch" bucket.
                content_prose_anomalies.append({"sha": c["sha"], "subject": c["subject"], "unexpected_file": f})

    # Step 3: current keyword-count snapshot by platform (sourcePath).
    kw_path = REPO_ROOT / "keywords" / f"{family}.json"
    keyword_snapshot = {"total_entries": 0, "by_platform": {}, "file_exists": kw_path.exists()}
    if kw_path.exists():
        try:
            data = json.loads(kw_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                keyword_snapshot["total_entries"] = len(data)
                by_platform: dict[str, int] = {}
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    src = entry.get("sourcePath", "")
                    parts = src.split("/")
                    platform = parts[1] if len(parts) > 1 else "unknown"
                    by_platform[platform] = by_platform.get(platform, 0) + 1
                keyword_snapshot["by_platform"] = by_platform
        except Exception as exc:
            keyword_snapshot["error"] = str(exc)

    # Step 4: real diffs for content/*.md touches (this mission has written
    # real content/ prose to exactly 2 files total, per the v10 audit, both
    # under pdf -- so this should be empty for every other family).
    content_diffs = []
    for touch in content_md_touches[:5]:
        r = run(["git", "show", touch["sha"], "--", touch["path"]])
        content_diffs.append({"sha": touch["sha"], "path": touch["path"], "diff": r.stdout[:4000]})

    return {
        "family": family,
        "seo_commits_touching_keywords_file": len(kw_commits),
        "seo_commits_touching_content": len(content_commits),
        "total_seo_commits_in_scope": len(commits),
        "commits": commits,
        "other_family_keywords_touches_count": len(other_family_keywords_touches),
        "other_family_keywords_touches_sample": other_family_keywords_touches[:5],
        "content_prose_anomalies": content_prose_anomalies,
        "keyword_snapshot": keyword_snapshot,
        "content_md_touches_count": len(content_md_touches),
        "content_diffs_sample": content_diffs,
    }


if __name__ == "__main__":
    family = sys.argv[1]
    out_path = sys.argv[2]
    pack = build_pack(family)
    Path(out_path).write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"family={family} seo_commits={pack['total_seo_commits_in_scope']} "
          f"other_family_keywords_touches={pack['other_family_keywords_touches_count']} "
          f"content_prose_anomalies={len(pack['content_prose_anomalies'])} "
          f"content_md_touches={pack['content_md_touches_count']}")
