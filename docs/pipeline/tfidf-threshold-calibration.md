# TF-IDF Threshold Calibration Notes

## Overview

Four pipeline features use TF-IDF cosine similarity thresholds. This document
records the rationale for each threshold, its calibration history, and when to
recalibrate.

All thresholds were set from first-principles analysis on Aspose product content.
Proper calibration against labeled datasets is deferred to TC-CALIB-001 Phase 2
(requires production data accumulation).

---

## 1. Prose Grounding Evaluator

**File**: `scripts/pipeline/content_eval/evaluators/prose_grounding.py`

| Constant | Value |
|----------|-------|
| `_SIMILARITY_THRESHOLD` | 0.25 |

**Rationale**: Lowered from 0.30 (TC-EVAL-001) to eliminate the 0.25-0.35 dead
zone where knowledge regeneration shifted TF-IDF term frequencies enough to flip
verdicts on consecutive runs.

**Behavioral boundary** (verified by tests in `test_prose_grounding.py::TestThresholdBoundary`):
- similarity >= 0.25 → no WARN (grounded claim)
- similarity < 0.25 → WARN (ungrounded claim)

**Recalibrate when**:
- Grade instability observed for claims scoring 0.20-0.30 across reruns
- Evaluator produces confirmed false positives on a new product family
- Token vocabulary expands significantly (new API domain or language platform)

**Calibration method**: Run prose_grounding on 200+ pages with manually labeled
grounded/ungrounded claims. Plot WARN rate vs similarity score. Set threshold at
the valley between the grounded and ungrounded score distributions.

---

## 2. Cross-Page Consistency Checker

**File**: `scripts/pipeline/commands/content/cross_page_consistency.py`

| Constant | Value |
|----------|-------|
| `_CLUSTER_THRESHOLD` | 0.60 |

**Rationale**: Two claims must share >=60% TF-IDF cosine similarity to be
considered "about the same topic" before checking for contradictions. Set at 0.60
to allow topic clustering across paraphrase variations while avoiding false
clusters between unrelated capabilities.

**Known risk**: With 2-document IDF corpus (only the two claims being compared),
shared terms are penalized less than in a full corpus. This may inflate similarity
scores. Real-world effective threshold may need to be lower (0.50) once calibrated
against real contradiction pairs.

**Recalibrate when**:
- More than 20% of flagged contradictions are false positives on manual review
- Legitimate contradictions are being missed (threshold too high)
- Claim corpus grows beyond 1000 claims per product (IDF distribution shifts)

**Calibration method**: Build labeled contradiction pairs (25 true, 25 false) per
product. Measure precision/recall across 0.50-0.75 threshold range. Target:
precision >=85%, recall >=80%.

---

## 3. Backlink Semantic Confirmation Layer

**File**: `scripts/pipeline/commands/ops/backlink_adjudicate_review.py`

| Constant | Value | Use |
|----------|-------|-----|
| `_SC_SIMILARITY_THRESHOLD` | 0.80 | Case A: unrelated + high score override |
| `_SC_ANCHOR_LOWER_THRESHOLD` | 0.65 | Case B: API class + low score lower bound |

**Case A** (`_SC_SIMILARITY_THRESHOLD = 0.80`): For "unrelated + high score"
escalated candidates, requires cosine >= 0.80 between source and target page texts
to reclassify as same_topic and promote. Conservative initial value.

**Case B** (`_SC_ANCHOR_LOWER_THRESHOLD = 0.65`): For "exact/related API class +
low score" candidates with valid anchors, lowers promotion threshold from 0.70 to
0.65.

**Known risk**: With TF-IDF's 2-document IDF corpus (source + target only), 0.80
requires near-identical vocabulary. Source pages use prose summaries; target pages
are API stubs — different register. Measured cosine between known-related page pairs
may be 0.40-0.60. The 0.80 threshold may produce zero Case A rescues on real data.

**Recommended validation**: Run `--semantic-confirm` on 50 known-related
ESCALATE_TO_OPERATOR candidates. Measure cosine distribution. If median cosine for
related pairs is < 0.60, lower `_SC_SIMILARITY_THRESHOLD` to 0.55-0.65.

**Recalibrate when**:
- Semantic confirm rescues fewer than 10% of tested candidates (too conservative)
- Human review shows >20% of rescues are wrong promotions (too permissive)

---

## Recalibration Procedure (General)

1. Collect labeled dataset: 50+ pairs with known ground truth (match/no-match)
2. Compute cosine similarity distribution for positive and negative cases
3. Find threshold at ROC curve point: precision >=90% and recall >=80%
4. Update constant in source file
5. Update boundary tests in corresponding test file
6. Add `# Recalibrated YYYY-MM-DD: <reason>` comment next to constant
7. Run full test suite; verify no regressions
8. Record update in calibration history below

---

## Calibration History

| Date | Feature | Old Value | New Value | Reason |
|------|---------|-----------|-----------|--------|
| 2026-06-11 | prose_grounding `_SIMILARITY_THRESHOLD` | 0.30 | 0.25 | TC-EVAL-001: eliminate 0.25-0.35 dead zone causing grade instability |
| 2026-06-11 | cross_page_consistency `_CLUSTER_THRESHOLD` | (new) | 0.60 | TC-CONSIST-001: first-principles estimate; requires real-data calibration |
| 2026-06-11 | backlink `_SC_SIMILARITY_THRESHOLD` | (new) | 0.80 | TC-BLINK-001: conservative initial; requires dead-zone sample calibration |
| 2026-06-11 | backlink `_SC_ANCHOR_LOWER_THRESHOLD` | (new) | 0.65 | TC-BLINK-001: 5-point relaxation for valid-anchor API candidates |
