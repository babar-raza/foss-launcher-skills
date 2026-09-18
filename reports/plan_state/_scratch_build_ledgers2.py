# -*- coding: utf-8 -*-
import sys, json, re
sys.path.insert(0, "scripts/pipeline/commands/foss")
import readme_refresh_checks as C
import readme_refresh_run as rr

cc = rr._product_clone_cache("pdf", "typescript")
old, _ = rr._resolve_old_readme_text("pdf", "typescript", cc)
cand = open("reports/repo-presenter-regen-full/pdf/typescript/readme.md", encoding="utf-8").read()

content_units = {u["unit_id"]: u for u in C.extract_old_readme_content_units(old)}
code_units = C.extract_old_readme_code_units(old)
structural_units = C.extract_old_readme_structural_units(old)
content_out = json.load(open("reports/plan_state/_content_pass1.json", encoding="utf-8"))

MANUAL_REFRAME = {
    "u0013": "Vector drawing", "u0016": "SVG embedding", "u0032": "Text replace",
    "u0047": "Tagged-PDF structure reading", "u0055": "PDF/X validation",
    "u0056": "PDF/X conversion", "u0069": "Digital signatures",
}
for row in content_out:
    if row.get("_needs_review") and row["unit_id"] in MANUAL_REFRAME:
        u = content_units[row["unit_id"]]
        row.clear()
        row.update({
            "unit_id": u["unit_id"], "source": "clone_cache/README.md", "excerpt": u["excerpt"],
            "salient_tokens": u.get("salient_tokens") or [], "classification": "2_mechanism_explanation",
            "classification_basis": f"real, checkable product-mechanism claim ({MANUAL_REFRAME[u['unit_id']]}); "
                "condensed into its Key Capabilities bullet -- the specific method-signature tokens don't survive "
                "verbatim, but the real capability, real class/method names, and real behavior are stated (verified "
                "by direct reading of the composed Key Capabilities bullet against this excerpt, not just token overlap)",
            "disposition": "merged_reframed", "target_section": "Key Capabilities",
            "verification": {"status": "verified_against_source", "evidence_type": "clone_cache_path",
                              "evidence_ref": "README.md"},
        })

# u0075: "To work from a clone instead..." -- real fact restored into Installation directly.
for row in content_out:
    if row.get("_needs_review") and row["unit_id"] == "u0075":
        u = content_units["u0075"]
        row.clear()
        row.update({
            "unit_id": "u0075", "source": "clone_cache/README.md", "excerpt": u["excerpt"],
            "salient_tokens": u.get("salient_tokens") or [], "classification": "2_mechanism_explanation",
            "classification_basis": "real installation-path fact (local file / npm workspace dependency), restored "
                "verbatim into the Installation section",
            "disposition": "merged_verbatim", "target_section": "Installation",
            "verification": {"status": "verified_against_source", "evidence_type": "clone_cache_path",
                              "evidence_ref": "README.md"},
        })

still_needs_review = [c for c in content_out if c.get("_needs_review")]
print("still needing review:", len(still_needs_review))
assert not still_needs_review, still_needs_review
assert len(content_out) == len(content_units) == 324, (len(content_out), len(content_units))

open("reports/repo-presenter-regen-full/pdf/typescript/content-dispositions.json", "w", encoding="utf-8", newline="\n").write(
    json.dumps(content_out, indent=2, ensure_ascii=False) + "\n"
)
print("content-dispositions.json written:", len(content_out), "entries")

# --- structural units (3) ------------------------------------------------------------------
def norm(s):
    s = s.lower(); s = re.sub(r"[`*_>#]", "", s)
    s = re.sub(r"[‘’]", "'", s); s = re.sub(r"[“”]", '"', s); s = re.sub(r"[–—]", "-", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

cand_norm = norm(cand)
print("\nstructural units:")
for s in structural_units:
    print(" ", s["unit_id"], s.get("heading"), s.get("kind"), "| verbatim:", norm(s.get("excerpt") or "")[:60] in cand_norm if s.get("excerpt") else "?")
    print("    ", json.dumps(s)[:300])
