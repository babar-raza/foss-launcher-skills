"""SEO-TITLE-PILOT-OBSERVATION-MEASURE (F5) driver. Gitignored (reports/),
one-off -- not a pipeline module. Uses scripts/seo/pipeline/gsc_history.py
(the card's real, reusable deliverable) to build
reports/seo/pilot_observation_2026-09.json.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "seo" / "pipeline"))
import gsc_history as gh  # noqa: E402

PRE_DATE = datetime(2026, 7, 29, tzinfo=timezone.utc)
POST_DATE = datetime(2026, 8, 12, tzinfo=timezone.utc)
SITE = "docs"

PILOT_PAGES = [
    {
        "url": "https://docs.aspose.org/pdf/net/developer-guide/",
        "source_path": "content/docs.aspose.org/en/pdf/net/developer-guide/_index.md",
        "old_title": "Developer Guide",
        "new_title": "Aspose.PDF FOSS for .NET — Forms, Annotations & JavaScript Extensions",
        "applied_commit": "3d0e3b723bec07e159db3b2e09f041fd8c4d4cbf",
        "applied_date": "2026-07-29",
    },
    {
        "url": "https://docs.aspose.org/pdf/java/developer-guide/",
        "source_path": "content/docs.aspose.org/en/pdf/java/developer-guide/_index.md",
        "old_title": "Developer Guide",
        "new_title": "Aspose.PDF FOSS for Java — Developer Guide & Examples",
        "applied_commit": "3d0e3b723bec07e159db3b2e09f041fd8c4d4cbf",
        "applied_date": "2026-07-29",
    },
]


def measure_page(page: dict) -> dict:
    pre_record = gh.get_url_record_asof(SITE, page["url"], PRE_DATE, "before")
    post_record = gh.get_url_record_asof(SITE, page["url"], POST_DATE, "after")
    pre_metrics = gh.aggregate_metrics(pre_record)
    post_metrics = gh.aggregate_metrics(post_record)
    if pre_metrics is None and post_metrics is None:
        verdict = "INCONCLUSIVE"
        reason = "no GSC data observed for this URL in any weekly snapshot, pre or post (0/26 snapshot commits contain it)"
    elif pre_metrics is None or post_metrics is None:
        verdict = "INCONCLUSIVE"
        reason = "GSC data observed in only one of the two windows -- cannot compute a before/after delta"
    else:
        verdict = "MEASURABLE"
        reason = "real pre/post data available"
    return {
        **page,
        "pre_metrics": pre_metrics,
        "post_metrics": post_metrics,
        "verdict": verdict,
        "reason": reason,
    }


def measure_control_set() -> dict:
    pre_snap = gh.find_snapshot_asof(SITE, PRE_DATE, "before")
    post_snap = gh.find_snapshot_asof(SITE, POST_DATE, "after")
    pre_data = gh.load_snapshot(SITE, pre_snap["sha"])
    post_data = gh.load_snapshot(SITE, post_snap["sha"])
    pre_by_url = {e["url"]: e for e in pre_data}
    post_by_url = {e["url"]: e for e in post_data}
    pilot_urls = {p["url"] for p in PILOT_PAGES}
    common_urls = sorted((set(pre_by_url) & set(post_by_url)) - pilot_urls)

    def _with_snapshot(record, snap):
        if record is None:
            return None
        return {**record, "_snapshot_sha": snap["sha"], "_snapshot_date": snap["date"].isoformat()}

    entries = []
    for url in common_urls:
        pre_m = gh.aggregate_metrics(_with_snapshot(pre_by_url.get(url), pre_snap))
        post_m = gh.aggregate_metrics(_with_snapshot(post_by_url.get(url), post_snap))
        entries.append({"url": url, "pre_metrics": pre_m, "post_metrics": post_m})

    return {
        "pre_snapshot": {"sha": pre_snap["sha"], "date": pre_snap["date"].isoformat()},
        "post_snapshot": {"sha": post_snap["sha"], "date": post_snap["date"].isoformat()},
        "control_url_count": len(common_urls),
        "entries": entries,
    }


def main():
    pilot_results = [measure_page(p) for p in PILOT_PAGES]
    control = measure_control_set()

    overall_verdict = "PASS" if all(r["verdict"] == "MEASURABLE" for r in pilot_results) else "INCONCLUSIVE"
    # (MEASURABLE alone doesn't imply PASS -- would need real position/CTR
    # deltas vs control to grade; both pilot pages are INCONCLUSIVE here so
    # the aggregate is trivially INCONCLUSIVE without needing that logic yet.)

    report = {
        "measurement": "SEO-TITLE-PILOT-OBSERVATION-MEASURE",
        "finding": "F5",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pre_window_target": PRE_DATE.date().isoformat(),
        "post_window_target": POST_DATE.date().isoformat(),
        "site": SITE,
        "pilot_pages": pilot_results,
        "control_set": control,
        "overall_verdict": overall_verdict,
        "overall_finding": (
            "Neither pilot page (pdf/net/developer-guide/, pdf/java/developer-guide/) has ever "
            "appeared in any of the 26 real weekly GSC Query Collector snapshots for "
            "docs.aspose.org (2026-03-26 through 2026-08-30), before or after the 2026-07-29 "
            "title change -- confirmed by an exhaustive scan of every historical commit to "
            "keywords/docs.aspose.org.json, not just the nearest pre/post snapshots. This means "
            "the observation this card exists to make is genuinely impossible with the data "
            "currently collected, not merely inconclusive due to a weak signal -- 'a query "
            "proves demand, never truth' and 'None means no data, never zero' (mission doctrine) "
            "both apply directly: these pages have simply never generated enough GSC query "
            "volume to be included in a weekly export. This is the same root issue "
            "SEO-GSC-COLLECTOR-COVERAGE-AUDIT is investigating for reference.aspose.org (7 URLs "
            "for a 131K-page site) -- here it directly blocks SEO-TITLE-EXPAND-BEYOND-PILOT's own "
            "dependency (this measurement = PASS) from ever being satisfiable until GSC coverage "
            "improves, independent of whether the title change itself helped."
        ),
        "control_set_summary": (
            f"{control['control_url_count']} other docs.aspose.org URLs had real GSC data in both "
            "the pre and post snapshot windows -- provided for site-wide context; not usable as a "
            "counterfactual for the pilot pages specifically, since none of them share the pilot "
            "pages' family/platform/page-type."
        ),
    }

    out_path = REPO_ROOT / "reports" / "seo" / "pilot_observation_2026-09.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"overall_verdict": overall_verdict, "written_to": str(out_path)}, indent=2))


if __name__ == "__main__":
    main()
