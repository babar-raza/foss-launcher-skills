# Adapted from aspose.org
"""section_enhance_validator.py — S-96 section-enhance Phase 1 audit output validator.

CONTRACT: pure library module — no CLI, no __main__, no subprocess, no os.system,
no writes outside paths explicitly passed into functions.

Validates the schema and behavioral contracts of S-96 section-enhance proposal
pack artifacts produced during Phase 1 audit runs.

What this module proves:
- All 10 required proposal-pack artifacts are present for a given run slug
- 00-run-manifest.json input_aliases entries each contain from/to/reason/evidence
- adapters_activated and adapters_NOT_activated are disjoint and contain only known adapters
- The expected adapter is activated for a given subdomain
- No files under content/ were created or modified during a run
- Zero-proposal runs are valid when all artifacts present and reason is non-empty
- Proposal slugs conform to kebab-case rules

What this module does NOT prove:
- That S-96 produces correct output on real targets
- That live S-96 invocation behavior is correct
- That generated code snippets compile against the actual library
- That internal API classes are correctly filtered from api_surface.json

Exported functions:
    validate_artifact_pack(pack_dir)
    validate_manifest_aliases(manifest)
    validate_adapter_activation(manifest, expected_primary_adapter)
    snapshot_content_mtimes(content_root)
    detect_content_writes(content_root, before_snapshot)
    validate_zero_proposal_run(manifest, pack_dir)
    validate_proposal_slug(slug)

Error codes (prefix on all error strings returned by validate_* functions):
    ERR-ALI-001  validate_manifest_aliases    input_aliases not a list
    ERR-ALI-002  validate_manifest_aliases    alias entry not a dict or missing required key
    ERR-ADP-000  validate_adapter_activation  adapters list not a list type
    ERR-ADP-001  validate_adapter_activation  primary adapter absent or incorrectly placed
    ERR-ADP-002  validate_adapter_activation  adapter in both activated and NOT_activated
    ERR-ADP-003  validate_adapter_activation  unknown adapter name
    ERR-ADP-004  validate_adapter_activation  unexpected cross-domain adapter (leak)
    ERR-ZPR-001  validate_zero_proposal_run   proposals_generated != 0
    ERR-ZPR-002  validate_zero_proposal_run   zero_proposal_reason missing or empty
    ERR-ZPR-003  validate_zero_proposal_run   05-proposals/ directory missing
    ERR-ZPR-004  validate_zero_proposal_run   05-proposals/ directory non-empty
    ERR-SLG-001  validate_proposal_slug       empty slug
    ERR-SLG-002  validate_proposal_slug       regex mismatch (generic)
    ERR-SLG-003  validate_proposal_slug       leading hyphen
    ERR-SLG-004  validate_proposal_slug       trailing hyphen
    ERR-SLG-005  validate_proposal_slug       uppercase characters
    ERR-SLG-006  validate_proposal_slug       underscore characters

Note: validate_artifact_pack returns a list of missing artifact names (not coded
error strings) so that callers can identify exact missing artifacts by name directly.
"""

import re
from pathlib import Path
from typing import Union

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_ARTIFACTS = [
    "00-run-manifest.json",
    "01-section-inventory.md",
    "02-clone-cache-truth-map.md",
    "03-gap-report.md",
    "03-gap-report.json",
    "04-candidate-list.md",
    "05-proposals",        # directory — checked as is_dir()
    "06-evidence-map.json",
    "07-risk-report.md",
    "08-verification-checklist.md",
    "09-handoff-notes.md",
]

KNOWN_ADAPTERS = frozenset({
    "docs",
    "kb",
    "products",
    "blog",
    "reference",
    "clone-cache",
    "sibling-content",
    "package-metadata",
})

REQUIRED_ALIAS_KEYS = frozenset({"from", "to", "reason", "evidence"})

# Subdomain -> expected primary adapter
SUBDOMAIN_PRIMARY_ADAPTER = {
    "docs": "docs",
    "kb": "kb",
    "products": "products",
    "blog": "blog",
    "reference": "reference",
}

# Regex for valid kebab-case slug
_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _e(code, msg):
    return f"[{code}] {msg}"


# ---------------------------------------------------------------------------
# TC-SE-01: Artifact completeness
# ---------------------------------------------------------------------------

def validate_artifact_pack(pack_dir: Union[str, Path]) -> tuple:
    """Check that a proposal-pack directory contains all 10 required artifacts.

    Args:
        pack_dir: Path to the run directory.

    Returns:
        (valid: bool, missing: list[str])
        valid is True only when all required artifacts are present.
        missing lists artifact names that are absent.
    """
    pack_dir = Path(pack_dir)
    missing = []

    for artifact in REQUIRED_ARTIFACTS:
        artifact_path = pack_dir / artifact
        if artifact == "05-proposals":
            if not artifact_path.is_dir():
                missing.append("05-proposals/")
        else:
            if not artifact_path.is_file():
                missing.append(artifact)

    return (len(missing) == 0, missing)


# ---------------------------------------------------------------------------
# TC-SE-02: Manifest alias fields
# ---------------------------------------------------------------------------

def validate_manifest_aliases(manifest: dict) -> tuple:
    """Check that input_aliases entries each contain the four required keys.

    Args:
        manifest: Parsed run manifest dict (from 00-run-manifest.json).

    Returns:
        (valid: bool, errors: list[str])
    """
    errors = []

    if "input_aliases" not in manifest:
        return (True, [])  # field is optional; absence is not an error

    aliases = manifest["input_aliases"]
    if not isinstance(aliases, list):
        return (False, [_e("ERR-ALI-001", "input_aliases must be a list")])

    for idx, alias in enumerate(aliases):
        if not isinstance(alias, dict):
            errors.append(_e("ERR-ALI-002", f"alias[{idx}] must be a dict"))
            continue
        for key in sorted(REQUIRED_ALIAS_KEYS):
            if key not in alias:
                errors.append(_e("ERR-ALI-002", f"alias[{idx}] missing key: {key}"))

    return (len(errors) == 0, errors)


# ---------------------------------------------------------------------------
# TC-SE-03: Adapter activation per subdomain
# ---------------------------------------------------------------------------

def validate_adapter_activation(manifest: dict, expected_primary_adapter: str) -> tuple:
    """Check that the correct adapter is activated for a given subdomain.

    Validates:
    - expected_primary_adapter is in adapters_activated
    - expected_primary_adapter is NOT in adapters_NOT_activated
    - adapters_activated and adapters_NOT_activated are disjoint
    - No unknown adapter names appear in either list
    - No other primary subdomain adapter leaked into adapters_activated

    Args:
        manifest: Parsed run manifest dict.
        expected_primary_adapter: The subdomain's primary adapter (e.g. "docs").

    Returns:
        (valid: bool, errors: list[str])
    """
    errors = []

    activated = manifest.get("adapters_activated", [])
    not_activated = manifest.get("adapters_NOT_activated", [])

    if not isinstance(activated, list):
        return (False, [_e("ERR-ADP-000", "adapters_activated must be a list")])
    if not isinstance(not_activated, list):
        return (False, [_e("ERR-ADP-000", "adapters_NOT_activated must be a list")])

    activated_set = set(activated)
    not_activated_set = set(not_activated)

    # Expected primary must be activated
    if expected_primary_adapter not in activated_set:
        errors.append(_e("ERR-ADP-001", f"expected adapter '{expected_primary_adapter}' not in adapters_activated"))

    # Expected primary must NOT be in not_activated
    if expected_primary_adapter in not_activated_set:
        errors.append(_e("ERR-ADP-001", f"expected adapter '{expected_primary_adapter}' incorrectly in adapters_NOT_activated"))

    # No overlap between the two lists
    overlap = activated_set & not_activated_set
    for name in sorted(overlap):
        errors.append(_e("ERR-ADP-002", f"adapter '{name}' appears in both adapters_activated and adapters_NOT_activated"))

    # Leak detection: no other primary subdomain adapter in activated
    other_primaries = set(SUBDOMAIN_PRIMARY_ADAPTER.values()) - {expected_primary_adapter}
    leaked = activated_set & other_primaries
    for name in sorted(leaked):
        errors.append(_e("ERR-ADP-004", f"unexpected adapter in activated: {name}"))

    # Unknown adapter names
    for name in sorted(activated_set - KNOWN_ADAPTERS):
        errors.append(_e("ERR-ADP-003", f"unknown adapter in activated: {name}"))
    for name in sorted(not_activated_set - KNOWN_ADAPTERS):
        errors.append(_e("ERR-ADP-003", f"unknown adapter in NOT_activated: {name}"))

    return (len(errors) == 0, errors)


# ---------------------------------------------------------------------------
# TC-SE-04: No-content-write detection utility
# ---------------------------------------------------------------------------

def snapshot_content_mtimes(content_root: Union[str, Path]) -> dict:
    """Record modification times for all files under content_root.

    Args:
        content_root: Root path to snapshot.

    Returns:
        dict mapping str(path) -> float(mtime)
    """
    content_root = Path(content_root)
    snapshot = {}
    if not content_root.exists():
        return snapshot
    for fpath in content_root.rglob("*"):
        if fpath.is_file():
            snapshot[str(fpath)] = fpath.stat().st_mtime
    return snapshot


def detect_content_writes(content_root: Union[str, Path], before_snapshot: dict) -> list:
    """Detect files under content_root that were created or modified since before_snapshot.

    Args:
        content_root: Same root passed to snapshot_content_mtimes.
        before_snapshot: dict from a prior snapshot_content_mtimes call.

    Returns:
        list[str] of file paths that are new or have a different mtime.
    """
    content_root = Path(content_root)
    changed = []
    if not content_root.exists():
        return changed
    for fpath in content_root.rglob("*"):
        if fpath.is_file():
            key = str(fpath)
            if key not in before_snapshot:
                changed.append(key)
            elif fpath.stat().st_mtime != before_snapshot[key]:
                changed.append(key)
    return changed


# ---------------------------------------------------------------------------
# TC-SE-05: Zero-proposal run validation
# ---------------------------------------------------------------------------

def validate_zero_proposal_run(manifest: dict, pack_dir: Union[str, Path]) -> tuple:
    """Check that a zero-proposal run is valid: reason present, proposals dir empty.

    Args:
        manifest: Parsed run manifest dict.
        pack_dir: Path to the run directory.

    Returns:
        (valid: bool, errors: list[str])
    """
    errors = []

    proposals_generated = manifest.get("proposals_generated", None)
    if proposals_generated != 0:
        errors.append(
            _e("ERR-ZPR-001", f"proposals_generated is {proposals_generated!r}, expected 0")
        )
        return (False, errors)

    # zero_proposal_reason must be present and non-empty
    reason = manifest.get("zero_proposal_reason", "")
    if not reason:
        errors.append(
            _e("ERR-ZPR-002", "zero_proposal_reason must explain why no proposals were generated")
        )

    # 05-proposals/ directory must exist but contain no proposal files
    proposals_dir = Path(pack_dir) / "05-proposals"
    if proposals_dir.is_dir():
        proposal_files = [
            f for f in proposals_dir.iterdir()
            if f.is_file() and f.name != ".gitkeep"
        ]
        if proposal_files:
            errors.append(_e("ERR-ZPR-004", f"proposals_generated is 0 but 05-proposals/ contains {len(proposal_files)} file(s)"))
    else:
        errors.append(_e("ERR-ZPR-003", "05-proposals/ directory is missing"))

    return (len(errors) == 0, errors)


# ---------------------------------------------------------------------------
# TC-SE-07: Slug validation
# ---------------------------------------------------------------------------

def validate_proposal_slug(slug: str) -> tuple:
    """Validate a proposal slug against kebab-case rules.

    Valid: lowercase letters, digits, hyphens; starts with a letter;
    no leading/trailing hyphens; no underscores; no uppercase.

    Args:
        slug: The slug string to validate (without .md extension).

    Returns:
        (valid: bool, error: str | None)
        error is None when valid is True.
    """
    if not slug:
        return (False, _e("ERR-SLG-001", "slug must not be empty"))

    if "_" in slug:
        return (False, _e("ERR-SLG-006", "slug must not contain underscores"))

    if slug != slug.lower():
        return (False, _e("ERR-SLG-005", "slug must be lowercase"))

    if slug.startswith("-"):
        return (False, _e("ERR-SLG-003", "slug must not start with hyphen"))

    if slug.endswith("-"):
        return (False, _e("ERR-SLG-004", "slug must not end with hyphen"))

    if not _SLUG_RE.match(slug):
        return (False, _e("ERR-SLG-002", "slug must match ^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"))

    return (True, None)
