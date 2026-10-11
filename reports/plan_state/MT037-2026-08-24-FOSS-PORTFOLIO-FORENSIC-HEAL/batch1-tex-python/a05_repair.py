import sys
sys.path.insert(0, "scripts/pipeline")
from lib.taskcard_store import TaskcardStore
from datetime import datetime, timezone

store = TaskcardStore("MT037-2026-08-24-FOSS-PORTFOLIO-FORENSIC-HEAL")
now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
sid = "e2e5e67b-0183-4cc6-b0b0-2e0b6d8898cf"

cards = [
    ("TC-tex-python-01-PROPAGATE-IMPORT-FIX", "RC-tex-python-03", [
        {"approach": "Propagate the exact proven exported_via_package_init/public_import_module instruction from new-docs-page.md to the 3 sibling skills, then fix the 2 already-affected pages",
         "correctness": "high: reuses a pattern already validated by MT028's real fix, not a new design",
         "scope": "narrow: 3 skill files + 2 content files",
         "maintainability": "good: single source-of-truth pattern repeated verbatim",
         "risk": "low", "repeatability": "high -- same instruction text, easy to re-verify via grep",
         "verification_cost": "low: grep -c on the 3 files + audit.py on the 2 pages",
         "selected": True},
        {"approach": "Build a single shared, importable curation-check module (e.g. a Python helper all 6 content-generation skills call) instead of duplicating the instruction text 4 times across skill docs",
         "correctness": "higher long-term (single source of truth, no drift risk)",
         "scope": "much broader: skills aren't code, they're LLM-prompt markdown -- would require redesigning how generation skills consult shared logic, not a text edit",
         "maintainability": "best in theory, but no existing mechanism for skills to import shared prompt-logic exists in this repo",
         "risk": "medium-high: novel mechanism, no precedent, larger blast radius for a single taskcard",
         "repeatability": "n/a until built",
         "verification_cost": "high: would need new tooling + tests for the mechanism itself",
         "selected": False},
    ]),
    ("TC-tex-python-02-DOCSTRING-RPREFIX", "RC-tex-python-04", [
        {"approach": "Fix _extract_doc_comment's quote-stripping to also strip a leading raw-string prefix, add a regression test, patch the one affected knowledge-model doc field directly, then regenerate only the dependent pages via batch_reference.py",
         "correctness": "high: fixes the exact root cause with a minimal, well-tested change",
         "scope": "narrow: 2 lines of production code + 1 knowledge field + 6 regenerated pages, all within tex/python",
         "maintainability": "good: isolated helper function, clear regression test",
         "risk": "low", "repeatability": "high -- the same fix protects every future extraction across all 31 products",
         "verification_cost": "low: 6 new unit tests + existing 40 api_surface tests re-run clean",
         "selected": True},
        {"approach": "Run a full re-scout (S-34 repo-scout) for tex/python to regenerate the entire knowledge model fresh with the fixed extraction code, instead of hand-patching the one affected field",
         "correctness": "high in principle (fully authoritative regeneration)",
         "scope": "very broad: knowledge_delta.json already showed 138 pending API changes and 520 pending claim changes for this product -- a full re-scout would pull all of that in, unreviewed, as a side effect of a docstring fix",
         "maintainability": "n/a -- one-time regeneration, doesn't reduce future risk",
         "risk": "high: would import 138+520 unrelated, unreviewed changes into a narrowly-scoped bug-fix taskcard",
         "repeatability": "n/a",
         "verification_cost": "very high: would require reviewing every one of the unrelated pending changes before trusting the result",
         "selected": False},
    ]),
    ("TC-tex-python-05-BLOG-CONTENT-FIX", "RC-tex-python-06", [
        {"approach": "Fix the 2 false PyPI-publication prose claims and the unverifiable Supported Formats table directly on the one affected blog post; leave the deeper audit.py-vs-content_eval coverage gap as a documented, disclosed machinery finding rather than fixing it inline",
         "correctness": "high for the immediate defect; content_eval independently confirms the install_recipe FAILs are fully resolved",
         "scope": "narrow: 1 content file",
         "maintainability": "n/a -- content fix, not a mechanism change",
         "risk": "low",
         "repeatability": "n/a to this specific claim (the underlying evaluator-coverage gap is tracked separately, not fixed by this option)",
         "verification_cost": "low: content_eval evaluate confirms install_recipe FAILs gone (format_truth FAILs on unrelated prose remain, disclosed separately)",
         "selected": True},
        {"approach": "Additionally wire gap-eval (or audit.py) to always dispatch to the full content_eval evaluator suite, closing the coverage gap that let this false claim survive undetected, as part of this same taskcard",
         "correctness": "would close the real root cause, not just the symptom",
         "scope": "very broad: affects every product's system-review pass campaign-wide, not just this one blog post",
         "maintainability": "good in principle, but needs its own careful design (which evaluators, what performance cost, how it interacts with gap-eval's tier system) -- not a same-taskcard afterthought",
         "risk": "medium: changing what tooling runs by default for every product is a campaign-wide behavior change that deserves its own dedicated investigation, not a rider on a single blog-post content fix",
         "repeatability": "high once built, but not appropriately scoped to build inside this taskcard",
         "verification_cost": "high: would need corpus-wide validation before trusting the new default dispatch",
         "selected": False},
    ]),
    ("TC-tex-python-03-COMPILE-CHECK-GAP", "RC-tex-python-05", [
        {"approach": "Add a new, narrowly-scoped module_compilability evaluator (Python-only, py_compile-based) registered EXPERIMENTAL per GRADE_CONTRACT.md section 6, verified live against the real tex/python defect",
         "correctness": "high: directly closes the exact proven gap (no evaluator checks whether a cited module can be imported at all)",
         "scope": "narrow: 1 new evaluator file + registration + tests, Python-only",
         "maintainability": "good: follows the exact BaseEvaluator/configure() seam conventions already established by sibling evaluators",
         "risk": "low: EXPERIMENTAL registration means it cannot affect any page's canonical grade until a maintainer graduates it after 14+ days corpus-wide validation",
         "repeatability": "high -- protects all 31 products going forward, not just tex/python",
         "verification_cost": "low: 6 new unit tests + live reproduction of the real tex/python defect",
         "selected": True},
        {"approach": "Build full multi-language compilability checking (javac, csc, g++, go build, rustc) in the same taskcard, so every platform is covered from day one, not just Python",
         "correctness": "would be more complete",
         "scope": "very broad: requires verifying toolchain availability across 5+ languages in this evaluation environment, plus per-language invocation/parsing logic",
         "maintainability": "unclear until each toolchain's real behavior in this environment is investigated",
         "risk": "high: could silently fail or behave inconsistently if a toolchain isn't actually installed here, and there's no evidence yet that any non-Python product has this exact defect class",
         "repeatability": "n/a until built and proven",
         "verification_cost": "very high: would need real fixtures and environment verification per language before trusting any of it",
         "selected": False},
    ]),
]

for task_id, rc_id, options in cards:
    prior = store.get(task_id)
    merged = dict(prior)
    merged["recorded_at"] = now
    merged["recorded_by"] = sid
    merged["options"] = options
    merged["note"] = ("A-05 repair (adversarial review, reviewer session cfc338a6-...): "
                       "retroactively documented >=2 scored options for this fix-plan item, "
                       "matching the discipline the formal S-122 fix-plan phase applied to "
                       "the first 2 taskcards.")
    r = store.append(merged)
    print("updated", r["task_id"], "with", len(options), "scored options")
