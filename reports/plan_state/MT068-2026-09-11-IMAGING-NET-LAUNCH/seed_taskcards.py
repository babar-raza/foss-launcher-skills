import sys
sys.path.insert(0, "scripts/pipeline")
from lib.taskcard_store import TaskcardStore

MISSION_ID = "MT068-2026-09-11-IMAGING-NET-LAUNCH"
RECORDED_BY = "session:69f58bf2-c7d9-4d98-8de9-1a947e4860e8"

store = TaskcardStore(MISSION_ID)

cards = [
    dict(
        task_id="TC-MT068-01",
        title="Register imaging/net in the product registry",
        objective="Add family=imaging, platform=net to data/products.json via /update-registry, "
                   "sourced from INV-019/IMAGING-NET-001 (repo aspose-imaging-foss/Aspose.Imaging.Foss).",
        lane="registry",
        priority="P1",
        allowed_paths=["data/products.json"],
        forbidden_paths=["content/", "knowledge/"],
        expected_outputs=["data/products.json contains an imaging/net entry with repo_url set"],
    ),
    dict(
        task_id="TC-MT068-02",
        title="Knowledge bootstrap for imaging/net",
        objective="Run /repo-scout (S-34) against aspose-imaging-foss/Aspose.Imaging.Foss to produce "
                   "knowledge/imaging/net/merged/{model.yaml,claims.json,api_surface.md,formats.json}, "
                   "then /truth-merge (S-36-ish promote) to finalize merged artifacts.",
        lane="knowledge",
        priority="P1",
        dependencies=["TC-MT068-01"],
        allowed_paths=["knowledge/imaging/net/"],
        expected_outputs=["knowledge/imaging/net/merged/model.yaml with real class_count/claims/snippets"],
    ),
    dict(
        task_id="TC-MT068-03",
        title="AGENTS.md §7d knowledge quality gate check",
        objective="Verify class_count>=5, total_claims>=20, snippet_count>=3, enrichment_status ok "
                   "against knowledge/imaging/net/merged/model.yaml before any content generation.",
        lane="knowledge",
        priority="P0",
        dependencies=["TC-MT068-02"],
        allowed_paths=[],
        expected_outputs=["Gate PASS recorded before Stage 0.5 of /launch-product"],
    ),
    dict(
        task_id="TC-MT068-04",
        title="Launch imaging/net across all 5 subdomains",
        objective="Run /launch-product imaging net (S-49): site-plan, then generate docs/kb/blog/"
                   "products/reference content, honoring the probe-only capability scope documented "
                   "in INV-019 (no decode/edit/convert claims).",
        lane="content",
        priority="P1",
        dependencies=["TC-MT068-03"],
        allowed_paths=["content/docs.aspose.org/", "content/kb.aspose.org/", "content/blog.aspose.org/",
                        "content/products.aspose.org/", "content/reference.aspose.org/"],
        expected_outputs=["Full 5-subdomain content set for imaging/net, S-23 content-check passing"],
    ),
    dict(
        task_id="TC-MT068-05",
        title="S-90 publish-readiness review for imaging/net",
        objective="Run /publish-readiness-review scoped to imaging/net across Tier 1/2 content before "
                   "declaring the launch complete.",
        lane="review",
        priority="P1",
        dependencies=["TC-MT068-04"],
        allowed_paths=[],
        expected_outputs=["S-90 verdict recorded; any FAILs routed back and closed"],
    ),
]

import datetime

for c in cards:
    rec = {
        "task_id": c["task_id"],
        "mission_id": MISSION_ID,
        "status": "TODO",
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "evidence_refs": [],
        "recorded_by": RECORDED_BY,
        "title": c["title"],
        "objective": c["objective"],
        "lane": c["lane"],
        "priority": c["priority"],
        "dependencies": c.get("dependencies", []),
        "allowed_paths": c.get("allowed_paths", []),
        "forbidden_paths": c.get("forbidden_paths", []),
        "expected_outputs": c.get("expected_outputs", []),
        "source_finding": "backlog/inbox.md INV-019 + backlog/BACKLOG.md IMAGING-NET-001 "
                           "(S-93 repo-patrol scan 2026-09-11, live-verified LAUNCHABLE)",
    }
    written = store.append(rec)
    print("appended", written["task_id"], written["status"])

print("done:", store.path)
