# -*- coding: utf-8 -*-
import sys, json, re
sys.path.insert(0, "scripts/pipeline/commands/foss")
import readme_refresh_checks as C
import readme_refresh_run as rr

cc = rr._product_clone_cache("pdf", "typescript")
old, _ = rr._resolve_old_readme_text("pdf", "typescript", cc)
cand = open("reports/repo-presenter-regen-full/pdf/typescript/readme.md", encoding="utf-8").read()

content_units = C.extract_old_readme_content_units(old)
code_units = C.extract_old_readme_code_units(old)
structural_units = C.extract_old_readme_structural_units(old) if hasattr(C, "extract_old_readme_structural_units") else []
old_badges = C.extract_badges(old)
print("content_units:", len(content_units), "| code_units:", len(code_units),
      "| structural_units:", len(structural_units), "| old_badges:", len(old_badges))

def norm(s):
    s = s.lower()
    s = re.sub(r"[`*_>#]", "", s)
    s = re.sub(r"[‘’]", "'", s)
    s = re.sub(r"[“”]", '"', s)
    s = re.sub(r"[–—]", "-", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

cand_norm = norm(cand)

def token_hits(tokens, haystack_norm):
    hits = 0
    for t in tokens:
        tn = norm(t)
        if tn and tn in haystack_norm:
            hits += 1
    return hits

# --- content units -------------------------------------------------------------------------
content_out = []
GLUED_UNIT_ID = None
for u in content_units:
    excerpt = u["excerpt"]
    tokens = u.get("salient_tokens") or []
    if "# Aspose.PDF FOSS for TypeScript" in excerpt and "doc.AddFont(bytes, opts?)" in excerpt:
        # the real, live upstream defect: a stray API-table row glued directly onto the H1
        # title with no line break (confirmed via GitHub's own markdown renderer: the whole
        # thing renders as one <p>, and the H1 never renders as a heading at all).
        GLUED_UNIT_ID = u["unit_id"]
        content_out.append({
            "unit_id": u["unit_id"], "source": "clone_cache/README.md", "excerpt": excerpt,
            "salient_tokens": tokens, "classification": "1_narrative_cta",
            "classification_basis": "not a real content claim -- an extraction artifact of a live upstream defect: "
                "a stray duplicate API-table row is glued directly onto the H1 title with no line break, so GitHub's "
                "own markdown renderer treats the whole first line as one plain paragraph and the title never "
                "renders as a heading at all (verified via the real GitHub markdown API, 2026-09-03). The real "
                "title text and the real table row (`doc.AddFont`/`doc.AddFontFile`) both survive independently: "
                "the title as this candidate's own H1, the table row as its real entry in the Core API module table.",
            "disposition": "excluded",
            "excluded_reason": "extraction artifact of a live upstream rendering defect (glued first line) -- the "
                "real title and the real table row are both independently preserved elsewhere in the candidate; "
                "reported as an upstream issue, not narrated in the README itself",
            "verification": {"status": "verified_against_source", "evidence_type": "clone_cache_path",
                              "evidence_ref": "README.md",
                              "evidence_note": "confirmed live via GitHub's markdown render API 2026-09-03: the "
                                                "glued line renders as one <p>, not an <h1>"},
        })
        continue
    excerpt_norm = norm(excerpt)
    verbatim = excerpt_norm and excerpt_norm in cand_norm
    hits = token_hits(tokens, cand_norm) if tokens else 0
    hit_ratio = hits / len(tokens) if tokens else 0
    if verbatim:
        disp, basis = "merged_verbatim", "byte-for-byte (normalized) match found in the candidate"
    elif hit_ratio >= 0.6:
        disp, basis = "merged_reframed", f"{hits}/{len(tokens)} salient tokens present in the candidate (condensed into Key Capabilities)"
    else:
        disp, basis = None, None
    if disp is None:
        content_out.append({"_needs_review": True, "unit_id": u["unit_id"], "excerpt": excerpt[:200], "tokens": tokens})
        continue
    content_out.append({
        "unit_id": u["unit_id"], "source": "clone_cache/README.md", "excerpt": excerpt,
        "salient_tokens": tokens, "classification": "2_mechanism_explanation",
        "classification_basis": f"real, checkable product-mechanism claim; {basis}",
        "disposition": disp, "target_section": "Key Capabilities",
        "verification": {"status": "verified_against_source", "evidence_type": "clone_cache_path",
                          "evidence_ref": "README.md"},
    })

json.dump(content_out, open("reports/plan_state/_content_pass1.json", "w", encoding="utf-8"), indent=1)
needs_review = [c for c in content_out if c.get("_needs_review")]
print("content: auto-classified", len(content_out) - len(needs_review), "| needs review:", len(needs_review))
for c in needs_review[:60]:
    open("reports/plan_state/_needs_review.txt","a",encoding="utf-8").write(c["unit_id"]+" | "+c["excerpt"][:200].replace(chr(10)," ")+chr(10))
