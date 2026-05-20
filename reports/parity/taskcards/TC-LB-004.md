# TC-LB-004: Create scripts/pipeline/lib/registry_loader.py stub

**ID**: LB-004
**Title**: Create scripts/pipeline/lib/registry_loader.py stub
**Purpose**: Create the registry_loader shared library module needed by backing scripts

## Scope
Port registry_loader.py from aspose.org's scripts/pipeline/lib/registry_loader.py with path adaptations.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/scripts/pipeline/lib/registry_loader.py

## Allowed Changes
- scripts/pipeline/lib/registry_loader.py

## Forbidden Changes
- Any other scripts
- skills/

## Dependencies
- VF-001

## Implementation Steps
1. Read D:/onedrive/Documents/GitHub/aspose.org/scripts/pipeline/lib/registry_loader.py
2. Identify all public functions (used by other modules)
3. Identify any aspose.org-specific path assumptions and replace with foss patterns
4. Create scripts/pipeline/lib/__init__.py if not exists
5. Write scripts/pipeline/lib/registry_loader.py with adapted implementation
6. Add module docstring documenting origin and adaptations

## Verification Steps
1. python -c 'from scripts.pipeline.lib import registry_loader' succeeds
2. All public functions exist and have correct signatures
3. No aspose.org-specific paths hardcoded

## Expected Artifacts
- scripts/pipeline/lib/registry_loader.py

**Risk**: MEDIUM — code change, may affect script behavior
**Rollback**: Delete scripts/pipeline/lib/registry_loader.py

## Done Criteria
- [ ] scripts/pipeline/lib/registry_loader.py exists
- [ ] Module imports without error
- [ ] Public API matches aspose.org version