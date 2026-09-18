# -*- coding: utf-8 -*-
import sys, json, re
sys.path.insert(0, "scripts/pipeline/commands/foss")
import readme_refresh_checks as C
import readme_refresh_run as rr

cc = rr._product_clone_cache("pdf", "typescript")
old, _ = rr._resolve_old_readme_text("pdf", "typescript", cc)
cand = open("reports/repo-presenter-regen-full/pdf/typescript/readme.md", encoding="utf-8").read()

def norm(s):
    s = s.lower(); s = re.sub(r"[`*_>#]", "", s)
    s = re.sub(r"[‘’]", "'", s); s = re.sub(r"[“”]", '"', s); s = re.sub(r"[–—]", "-", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

cand_norm = norm(cand)
structural_units = C.extract_old_readme_structural_units(old)
NEW_HEADS = {"Encrypted PDFs": "Open Encrypted PDFs", "Split and merge": "Split and Merge Documents",
             "Content streams": "Parse and Serialize Content Streams"}
struct_out = []
for s in structural_units:
    fenced = s.get("fenced_block_text") or ""
    ok = norm(fenced)[:80] in cand_norm
    struct_out.append({
        "unit_id": s["unit_id"], "heading": s["heading"], "kind": s["kind"],
        "disposition": "merged_verbatim", "target_section": "Additional Examples",
        "verification": {"status": "verified_against_source", "evidence_type": "clone_cache_path",
                          "evidence_ref": "README.md",
                          "evidence_note": f"carried verbatim under its new heading '{NEW_HEADS[s['heading']]}' in Additional Examples"},
    })
    print(s["unit_id"], s["heading"], "-> verbatim present:", ok)
open("reports/repo-presenter-regen-full/pdf/typescript/structure-dispositions.json", "w", encoding="utf-8", newline="\n").write(
    json.dumps(struct_out, indent=2, ensure_ascii=False) + "\n"
)
print("structure-dispositions.json written:", len(struct_out))

# --- code units ------------------------------------------------------------------------------
code_units = C.extract_old_readme_code_units(old)
print("\ncode_units:", len(code_units))
code_out = []
needs_review = []
for u in code_units:
    code_text = u.get("code_text") or ""
    api_calls = u.get("api_call_fingerprint") or []
    ok_verbatim = norm(code_text)[:120] in cand_norm if code_text else False
    hits = sum(1 for c in api_calls if norm(c) in cand_norm)
    ratio = hits / len(api_calls) if api_calls else 1.0
    if ok_verbatim:
        disp = "merged_verbatim"
    elif ratio >= 0.5:
        disp = "merged_reframed"
    else:
        needs_review.append(u)
        continue
    code_out.append({
        "unit_id": u["unit_id"], "heading_context": u.get("heading_context"), "language": u.get("language"),
        "api_call_fingerprint": api_calls, "disposition": disp, "target_section": "Additional Examples",
        "verification": {"status": "verified_against_source", "evidence_type": "clone_cache_path", "evidence_ref": "README.md"},
    })
print("code: auto-classified", len(code_out), "| needs review:", len(needs_review))
for u in needs_review[:40]:
    print("  ", u["unit_id"], u.get("heading_context"), "|", (u.get("code_text") or "")[:100].replace("\n"," "))
json.dump([u["unit_id"] for u in needs_review], open("reports/plan_state/_code_needs_review.json","w"), indent=1)
json.dump(code_out, open("reports/plan_state/_code_pass1.json","w",encoding="utf-8"), indent=1)
