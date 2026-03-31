# Plan Sources

## PrimaryPlanSource
- **Path**: `C:\Users\prora\.claude\plans\floating-imagining-bunny.md`
- **Type**: Chat-derived + disk plan (approved by user)
- **Rationale**: 25 actionable steps, 10 validation gates (G-1 through G-10), full acceptance criteria, concrete evidence commands. Meets SUBSTANTIAL threshold (>=5 steps, acceptance criteria + evidence commands).

## ChatExtractedSteps
1. WS0: Pre-flight baseline tests + branch creation
2. WS1: Extend config_loader.py with content_root, knowledge_root, reports_root
3. WS2: Create scripts/pipeline/ subpackage; import + adapt pipeline core scripts
4. WS3: Import content_eval/ package and scout_enrichers/
5. WS4: Replace all skill .md files; import 6 new skills; run distribute.py
6. WS5: Import AGENTS.md, CLAUDE.md, CODEX.md (adapted)
7. WS6: Run all 10 validation gates; merge branch

## ChatExtractedGapsAndFixes
- **G1**: CWD-relative path hardcoding in all pipeline scripts → fix via config_loader adapter
- **G2**: content_eval/cli.py imports audit.py via parent.parent → fix sys.path to scripts/pipeline/
- **G3**: Platform naming `dotnet` vs `net` discrepancy → add `net` alias in families.yaml
- **G4**: Missing knowledge/ data at runtime → document bootstrap requirement
- **G5**: Test import paths after script reorganization → update all 20 test files as needed

## ChatMentionedFiles
- `scripts/config_loader.py` (extend)
- `config.yaml` (add keys: content_root, knowledge_root, reports_root)
- `configs/schemas/config.schema.json` (update)
- `tests/test_config_loader.py` (update)
- `skills/` (replace all 36+)
- `scripts/pipeline/` (create)
- `AGENTS.md`, `CLAUDE.md`, `CODEX.md` (import/adapt)
- `tools/distribute.py` (verify)
- Source: `C:/Users/prora/OneDrive/Documents/GitHub/aspose.org/scripts/pipeline/`

## SubstantialityCheck
SUBSTANTIAL: 25 actionable steps, 10 validation gates, acceptance criteria, evidence commands ✓

## ResolutionStrategy
Execute plan directly from disk file. Chat instructions = orchestrator protocol wrapper.

## SecondarySources
- `AGENTS.md` (repo governance)
- `README.md` (project documentation)
- `pytest.ini` (test config)

## MissingCandidates
None — primary plan is complete and approved.
