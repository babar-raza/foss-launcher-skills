# Runbook: Stale Knowledge Model Recovery

**Version:** 1.0
**Last updated:** 2026-06-11
**Severity tiers:** P1 (content generation blocked), P2 (existing content may be outdated)

---

## Overview

This runbook covers recovery when a product knowledge model (`knowledge/{family}/{platform}/model.yaml`) has gone stale. Stale models block content generation to prevent fabricated claims based on outdated evidence.

---

## Staleness Detection

### Automatic detection (CI)

The skill-governance workflow runs stale detection on every push. Check the `skill-governance.yml` workflow logs for stale model warnings.

### Manual detection

```bash
# Check all model.yaml files for stale_since != null
grep -r "stale_since:" knowledge/ | grep -v "null"

# Or use the stale detection skill
python apply.py --skill S-13
```

A model is stale if any of the following are true:
- `stale_since` field is set in `model.yaml`
- The source FOSS repository has commits newer than the last knowledge update
- An API surface scan shows new methods/classes not in the model

---

## Recovery Procedure

### Step 1: Verify the stale model

```bash
cat knowledge/<family>/<platform>/model.yaml | grep -A3 "stale_since"
```

### Step 2: Re-clone or update the source repository

```bash
# Check the clone cache
ls .cloned/<org>/<repo>/

# Update the clone
cd .cloned/<org>/<repo>
git pull origin main
cd -
```

### Step 3: Run the knowledge update workflow

```bash
# S-12: Detect changes in the upstream repository
python apply.py --skill S-12 --family <family> --platform <platform>

# S-14: Refresh the knowledge model
python apply.py --skill S-14 --family <family> --platform <platform>

# Verify the model is no longer stale
python -c "
import yaml
with open('knowledge/<family>/<platform>/model.yaml') as f:
    m = yaml.safe_load(f)
assert m.get('stale_since') is None, 'Model still stale!'
print('Model is fresh:', m.get('updated_at'))
"
```

### Step 4: Update affected content pages

After the knowledge model is fresh, content pages that were blocked can now be generated or updated:

```bash
# Identify affected pages
python apply.py --skill S-13 --report  # shows affected content paths

# Run stale content update
python apply.py --skill S-20 --family <family> --platform <platform>
```

### Step 5: Verify no overclaims

After content update, run ground-check to verify all claims are still grounded:

```bash
python apply.py --skill S-23 --family <family> --platform <platform>
```

---

## Prevention

1. **CI enforcement**: The `skill-governance.yml` workflow runs S-13 on every push and fails if stale models are found without acknowledgment.
2. **Stale-since field**: When manually updating a model, always set `stale_since: null` and `updated_at: <ISO date>`.
3. **Clone cache freshness**: The `.cloned/` directory should be refreshed when running knowledge update skills. Do not rely on stale clone caches.

---

## Known Stale Patterns

| Pattern | Cause | Resolution |
|---------|-------|-----------|
| `stale_since` set after S-12 | Upstream repo has new commits | Run S-14 |
| `stale_since` set after manual edit | Human edited model.yaml without refreshing evidence | Re-run S-35 (truth-merge) |
| All platforms stale simultaneously | Major upstream release | Run S-12 + S-14 for each platform |

---

## Escalation

If S-14 fails or the model remains stale after recovery:

1. Check that the source repository is accessible: `git ls-remote <repo-url>`
2. Check that `configs/families.yaml` has the correct `repo_url` for the family.
3. Open a backlog item with `severity: P1`.
4. Ping the maintainer in `CODEOWNERS` for the `knowledge/<family>/` path.
