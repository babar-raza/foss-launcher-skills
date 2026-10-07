"""fleet_drift.py -- clone-free fleet drift classifier (MT074 B10 + B12).

CONTRACT: scripts/pipeline/commands/diagnostics/fleet_drift.py
  purpose: For every active product in data/products.json answer, WITHOUT cloning anything:
             "has upstream moved past the knowledge we built content from, how far, and does the
              change touch the public API?"
           Inputs per product: knowledge_sha (knowledge/{f}/{p}/merged/model.yaml `repo_sha`),
           the data/upstream_baselines.json sha, upstream HEAD (`git ls-remote`), the GitHub
           compare API (knowledge_sha...HEAD, paginated, truncation-aware) and the release state
           from data/package_registry.json (+ optional live registry probe).
  tiers:   NO_CHANGE | NON_SOURCE | SOURCE | API_TOUCHED | UNKNOWN, decided from the per-language
           source extensions / API-path globs in config/language_api_paths.yaml (keyed by the
           `platform` value of products.json). UNKNOWN is the safe default: unknown platform,
           truncated compare with no API file in view, orphaned baseline, rate-limit / auth /
           timeout, upstream behind the baseline. The tier is never guessed.
           `tier` measures drift of upstream HEAD against the KNOWLEDGE baseline. Whether content
           still needs work is a different question (a knowledge-only refresh makes tier NO_CHANGE
           while no page was ever reconciled), so for every product whose propagation status is not
           PROPAGATED the row also carries a `propagation_*` tier: derived from
           content_propagated_sha..HEAD (compare API) when a gate-verified propagated sha exists,
           else UNKNOWN-BASELINE ("never propagated": there is nothing to compare against).
  repo status: ok | no_knowledge | orphaned_baseline (the repository IS reachable via ls-remote
           but the baseline sha is gone from the compare API: force-push / gc) | repo_unreachable
           (ls-remote itself 404s / is denied: renamed, deleted or no access -- a different
           problem, no issue is filed, listed in the report) | error (transient: rate limit,
           auth, timeout, network).
  outputs: deterministic ledger JSON + Markdown (sorted keys; wall-clock values only under a
           `volatile` key), a sweep_report.json-compatible file (repo_patrol's schema, so
           /discovery-triage can consume it) via --sweep-out, optional state writes through
           content_propagation_state.record_drift (never propagation fields), optional ONE
           deduplicated GitHub issue per product titled `FLEET-PROPAGATE-{family}-{platform}`.
  issues:  filed for SOURCE / API_TOUCHED / UNKNOWN drift AND for products that were never
           propagated (tier UNKNOWN-BASELINE, labelled `never-propagated`, ranked last). Closed
           only when the state says PROPAGATED (PROPAGATED_LOCAL is not pushed: stays open).
           New issues and edits have SEPARATE budgets (--max-issues-per-run, --max-edits-per-run)
           so existing stale issues can never starve new products; creates run first, edits go
           oldest-updated first. Volatile facts (HEAD / knowledge sha, ahead_by, file counts) sit
           behind a marker line and are excluded from the staleness comparison (CRLF-normalised).
           `gh issue list` reaching its limit is an error, never a silent miss.
  state:   --update-state writes through record_drift ONLY when the write is real: never with
           --dry-run, and never with --offline unless an explicit --state-file points elsewhere
           (an offline fixture run must not be able to touch the real state file).
  B12:     per product `baseline_stores_disagree` (model.yaml sha vs upstream_baselines.json) and a
           fleet summary; optional `regen_baseline_projections.py check-staleness --json` result.
           Read-only: no repair behaviour.
  seams:   every git / gh / registry call goes through an injected runner / fetch (offline
           fixtures via --offline), `configure()` redirects paths. Nothing here names a product,
           family or language except via the YAML config.

Usage:
    python scripts/pipeline/commands/diagnostics/fleet_drift.py [--products f/p ...]
        [--json-out PATH] [--md-out PATH] [--sweep-out PATH] [--update-state]
        [--file-issues --repo OWNER/REPO] [--max-issues-per-run N] [--max-edits-per-run N]
        [--release-trigger f/p] [--offline FIXTURES_DIR] [--state-file PATH] [--dry-run]
        [--probe-registry] [--check-projections] [--workers N]

Exit codes: 0 ok, 1 an issue operation failed, 2 configuration error,
            4 state file unreadable / unwritable / corrupt / lock timeout (reports and issues are
            written and reported BEFORE the state write; the state file is left untouched).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import content_propagation_state as cps  # noqa: E402
import language_adapters as la  # noqa: E402
import publication_probe  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = _DEFAULT_REPO_ROOT
PRODUCTS_PATH = REPO_ROOT / "data" / "products.json"
BASELINES_PATH = REPO_ROOT / "data" / "upstream_baselines.json"
REGISTRY_PATH = REPO_ROOT / "data" / "package_registry.json"
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
_cfg_record_drift = None  # test seam: replaces content_propagation_state.record_drift in update_state
REGEN_SCRIPT = _PIPELINE_ROOT / "commands" / "ops" / "regen_baseline_projections.py"

SCHEMA_VERSION = 1
ISSUE_PREFIX = "FLEET-PROPAGATE"
COMPARE_PAGE_SIZE = 100
COMPARE_MAX_PAGES = 4
API_FILES_SAMPLE = 25
TRANSIENT_KINDS = frozenset({"rate_limited", "auth_error", "timeout", "tool_missing", "network_error"})
ORPHAN_KINDS = frozenset({"no_common_ancestor", "not_found"})    # only meaningful once ls-remote proved the repo reachable
UNREACHABLE_KINDS = frozenset({"not_found", "auth_error"})        # ls-remote itself failed this way: repo 404 / no access
ISSUE_LIST_LIMIT = 1000
VOLATILE_MARKER = "<!-- fleet-propagate:volatile (excluded from the staleness comparison) -->"
NEVER_PROPAGATED_LABEL = "never-propagated"
EXIT_STATE = 4

Runner = Callable[..., Any]


def configure(*, repo_root: "Path | str | None" = None, record_drift=None) -> None:
    """Override module-level path constants for testing (None restores the defaults). Also
    points content_propagation_state at <repo_root>/data/content_propagation_state.json."""
    global REPO_ROOT, PRODUCTS_PATH, BASELINES_PATH, REGISTRY_PATH, KNOWLEDGE_ROOT, _cfg_record_drift
    _cfg_record_drift = record_drift
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    PRODUCTS_PATH = REPO_ROOT / "data" / "products.json"
    BASELINES_PATH = REPO_ROOT / "data" / "upstream_baselines.json"
    REGISTRY_PATH = REPO_ROOT / "data" / "package_registry.json"
    KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
    cps.configure(REPO_ROOT / "data" / "content_propagation_state.json" if repo_root is not None else None)


# ── small readers ────────────────────────────────────────────────────────────

_REPO_URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")  # repo names contain dots


def parse_owner_repo(url: "str | None") -> "tuple[str | None, str | None]":
    m = _REPO_URL_RE.search(url or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def load_active_products(selected: "list[str] | None" = None) -> "list[dict[str, Any]]":
    products = _read_json(PRODUCTS_PATH, None)
    if not isinstance(products, list):
        raise FileNotFoundError(f"{PRODUCTS_PATH} missing or not a list")
    active = [p for p in products if p.get("active", False)]
    if selected:
        wanted = set(selected)
        known = {f"{p['family']}/{p['platform']}" for p in active}
        unknown = sorted(wanted - known)
        if unknown:
            raise ValueError(f"unknown or inactive product(s): {', '.join(unknown)}")
        active = [p for p in active if f"{p['family']}/{p['platform']}" in wanted]
    return sorted(active, key=lambda p: (p["family"], p["platform"]))


def read_model_sha(family: str, platform: str) -> "tuple[bool, str | None]":
    """(model.yaml exists, repo_sha or None). Line scan: model.yaml files are large."""
    model = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if not model.is_file():
        return False, None
    try:
        for line in model.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("repo_sha:"):
                value = line.split(":", 1)[1].strip().strip("'\"")
                return True, (value or None)
    except OSError:
        pass
    return True, None


# ── runner plumbing ──────────────────────────────────────────────────────────

def classify_error(text: str, returncode: int) -> str:
    """Map gh/git failure output to a stable kind. A bare 404 is only `not_found`: whether that
    means "orphaned baseline" (repository reachable, base sha gone) or "repository unreachable"
    is decided by the CALLER from which command failed (analyze_product), never from the text."""
    t = (text or "").lower()
    if returncode == 124 or "timeout" in t or "timed out" in t:
        return "timeout"
    if returncode == 127 or "cannot run" in t or "command not found" in t:
        return "tool_missing"
    if "rate limit" in t or "http 429" in t or "abuse detection" in t:
        return "rate_limited"
    if ("http 401" in t or "bad credentials" in t or "gh auth login" in t or "authentication" in t
            or "http 403" in t or "resource not accessible" in t or "could not read username" in t):
        return "auth_error"
    if "no common ancestor" in t:
        return "no_common_ancestor"
    if "http 404" in t or "not found" in t:
        return "not_found"
    if "could not resolve host" in t or "connection" in t or "network" in t or "unable to access" in t:
        return "network_error"
    return "gh_error"


def _err_text(res: Any) -> str:
    return ((getattr(res, "stderr", "") or "") + " " + (getattr(res, "stdout", "") or "")).strip()


def _short(text: str, n: int = 160) -> str:
    return " ".join((text or "").split())[:n]


def git_head(clone_url: str, *, runner: Runner) -> "tuple[str | None, dict | None]":
    res = runner(["git", "ls-remote", clone_url, "HEAD"], timeout=60)
    if res.returncode != 0:
        text = _err_text(res)
        return None, {"kind": classify_error(text, res.returncode), "message": _short(text)}
    toks = (res.stdout or "").split()
    if not toks:
        return None, {"kind": "gh_error", "message": "git ls-remote returned no HEAD"}
    return toks[0], None


def fetch_compare(owner: str, repo: str, base: str, head: str, *, runner: Runner,
                  max_visible: int = 300) -> "dict[str, Any]":
    """Paginated compare. Returns {status, ahead_by, files, files_seen, truncated, error}.
    `truncated` is True when files_seen >= max_visible (GitHub caps the list at 300 files)."""
    files: list[str] = []
    status = ahead = None
    for page in range(1, COMPARE_MAX_PAGES + 1):
        res = runner(["gh", "api", f"repos/{owner}/{repo}/compare/{base}...{head}"
                      f"?per_page={COMPARE_PAGE_SIZE}&page={page}"], timeout=90)
        if res.returncode != 0:
            text = _err_text(res)
            return {"status": status, "ahead_by": ahead, "files": files, "files_seen": len(files),
                    "truncated": False, "error": {"kind": classify_error(text, res.returncode), "message": _short(text)}}
        try:
            data = json.loads(res.stdout or "{}")
        except json.JSONDecodeError:
            return {"status": status, "ahead_by": ahead, "files": files, "files_seen": len(files),
                    "truncated": False, "error": {"kind": "gh_error", "message": "unparseable compare response"}}
        status, ahead = data.get("status"), data.get("ahead_by")
        page_files = data.get("files") or []
        files += [f["filename"] for f in page_files if f.get("filename")]
        if len(page_files) < COMPARE_PAGE_SIZE:
            break
    return {"status": status, "ahead_by": ahead, "files": files, "files_seen": len(files),
            "truncated": len(files) >= max_visible, "error": None}


class FixtureRunner:
    """Offline runner backed by recorded responses: <dir>/<owner>__<repo>.json =
    {"head": sha, "ls_remote_error": str|null, "compare": {"error": str|null, "pages": [raw compare
    API response per page ...], "by_base": {base_sha: {"error"|"pages": ...}}}}. `by_base` answers
    a compare for that specific base sha and wins over the default. Answers `git ls-remote` and
    `gh api .../compare/...`; every other command fails with rc 127."""

    def __init__(self, directory: "Path | str"):
        self.dir = Path(directory)
        self.calls: list[list[str]] = []

    def _load(self, owner: str, repo: str) -> "dict | None":
        p = self.dir / f"{owner}__{repo}.json"
        return _read_json(p, None) if p.is_file() else None

    @staticmethod
    def _cp(cmd, rc, out="", err=""):
        import subprocess
        return subprocess.CompletedProcess(cmd, rc, out, err)

    def __call__(self, cmd, *, cwd=None, timeout=None, env=None):
        self.calls.append(list(cmd))
        if cmd[:2] == ["git", "ls-remote"]:
            owner, repo = parse_owner_repo(cmd[2])
            fx = self._load(owner, repo) if owner else None
            if fx is None:
                return self._cp(cmd, 128, "", f"fixture missing for {cmd[2]}")
            if fx.get("ls_remote_error"):
                return self._cp(cmd, 128, "", fx["ls_remote_error"])
            return self._cp(cmd, 0, f"{fx['head']}\tHEAD\n")
        if cmd[:2] == ["gh", "api"]:
            m = re.match(r"repos/([^/]+)/([^/]+)/compare/([^.?]+)\.\.\.[^?]+\?per_page=\d+&page=(\d+)", cmd[2])
            if m:
                fx = self._load(m.group(1), m.group(2))
                if fx is None or "compare" not in fx:
                    return self._cp(cmd, 1, "", f"fixture missing for compare {m.group(1)}/{m.group(2)}")
                cmpfx = (fx["compare"].get("by_base") or {}).get(m.group(3)) or fx["compare"]
                if cmpfx.get("error"):
                    return self._cp(cmd, 1, "", cmpfx["error"])
                pages = cmpfx.get("pages") or []
                idx = int(m.group(4)) - 1
                page = pages[idx] if idx < len(pages) else {"status": "ahead", "ahead_by": 0, "files": []}
                return self._cp(cmd, 0, json.dumps(page))
        return self._cp(cmd, 127, "", f"cannot run {cmd[0]}: offline fixture runner")


# ── classification ───────────────────────────────────────────────────────────

def classify_tier(platform: str, compare: "dict[str, Any]", *, config: "dict[str, Any]") -> "dict[str, Any]":
    """Tier for one successful compare result."""
    files = compare["files"]
    max_visible = int((config.get("truncation") or {}).get("max_files_visible", 300))
    truncated = bool(compare["truncated"]) or compare["files_seen"] >= max_visible
    cls = la.classify_paths(platform, files, config=config)
    base = {"truncated": truncated, "source_files": len(cls["source_files"]),
            "api_files": cls["api_files"][:API_FILES_SAMPLE], "api_surface_touched": bool(cls["api_files"])}
    if compare.get("status") == "behind":
        return {**base, "tier": "UNKNOWN", "reason": "upstream_behind_baseline", "api_surface_touched": False}
    if not files and not truncated:
        return {**base, "tier": "NO_CHANGE", "reason": "no_file_changes"}
    if not cls["known_platform"]:
        unk = (config.get("unknown_platform") or {})
        return {**base, "tier": unk.get("tier", "UNKNOWN"), "reason": cls["unknown_reason"],
                "api_surface_touched": False}
    if cls["api_files"]:
        return {**base, "tier": "API_TOUCHED", "reason": "api_path_files_changed"}
    if truncated:
        return {**base, "tier": "UNKNOWN", "reason": "truncated_compare_incomplete"}
    if cls["source_files"]:
        return {**base, "tier": "SOURCE", "reason": "source_changed_outside_api_paths"}
    return {**base, "tier": "NON_SOURCE", "reason": "only_non_source_files_changed"}


def compute_release_state(install_info: "dict | None", upstream_head: "str | None", *,
                          probe: "dict | None" = None) -> "tuple[str, str]":
    """('released'|'unreleased_main'|'unknown', reason). Anything ambiguous is 'unknown'.

    released        published AND upstream HEAD is the commit the registry says was released
    unreleased_main published AND HEAD is ahead of the released commit
    The released commit is data/package_registry.json `candidate.repo_sha`. With a live probe
    the registry record is only trusted while the live latest version still equals
    `candidate.version`; a stale record can no longer name the released commit.
    """
    info = install_info or {}
    rtype = info.get("registry_type")
    if not rtype:
        return "unknown", "no_registry_entry"
    if rtype not in publication_probe._ADAPTERS and rtype != "maven":  # noqa: SLF001 -- supported-registry list
        return "unknown", "unsupported_registry"
    cand = info.get("candidate") or {}
    published = bool((info.get("verification") or {}).get("published"))
    if probe is not None:
        live = probe.get("live") or {}
        if probe.get("source") != "live_probe" or live.get("ambiguous"):
            return "unknown", "live_probe_ambiguous"
        published = bool(probe.get("effective_published"))
        live_ver, rec_ver = live.get("latest_version"), cand.get("version")
        if published and live_ver and rec_ver and live_ver != rec_ver:
            return "unknown", "registry_version_stale_vs_live"
    if not published:
        return "unknown", "not_published"
    release_sha = cand.get("repo_sha")
    if not release_sha:
        return "unknown", "no_release_sha"
    if not upstream_head:
        return "unknown", "no_upstream_head"
    if upstream_head == release_sha:
        return "released", "head_is_release_commit"
    return "unreleased_main", "head_ahead_of_release_commit"


class Context:
    def __init__(self, *, runner: Runner, config: "dict[str, Any]", baselines: "dict[str, str]",
                 registry: "dict[str, Any]", probe_fetch: "Callable | None" = None, probe: bool = False,
                 state_lookup: "Callable[[str, str], dict | None] | None" = None):
        self.runner, self.config, self.baselines, self.registry = runner, config, baselines, registry
        self.probe_fetch, self.probe = probe_fetch, probe
        self.state_lookup = state_lookup or (lambda family, platform: None)

    @property
    def max_visible(self) -> int:
        return int((self.config.get("truncation") or {}).get("max_files_visible", 300))


_SHA40 = re.compile(r"[0-9a-f]{40}")


def _trusted_propagated_sha(rec: "dict | None") -> "str | None":
    """A propagated sha is only a usable baseline when the record is gate-verified (PASS) -- a
    hand-edited sha is never trusted."""
    sha = (rec or {}).get("content_propagated_sha")
    if sha and (rec or {}).get("gate_verdict") == "PASS" and _SHA40.fullmatch(str(sha)):
        return sha
    return None


def _derive_propagation(row: "dict[str, Any]", entry: "dict[str, Any]", ctx: Context) -> None:
    """Fill the row's propagation_* fields (status, basis, tier).

    status PROPAGATED / PROPAGATED_LOCAL  -> basis `current` (no propagation tier needed)
    gate-verified propagated sha          -> compare content_propagated_sha...HEAD, classify
    otherwise                             -> basis `never_propagated`, tier UNKNOWN-BASELINE
    """
    rec = ctx.state_lookup(row["family"], row["platform"]) or {}
    row["propagation_status"] = cps.compute_status({**rec, "upstream_head": row["upstream_head"]})
    row["propagation_basis"] = "current"
    if row["propagation_status"] in ("PROPAGATED", "PROPAGATED_LOCAL"):
        return
    psha = _trusted_propagated_sha(rec)
    if not psha or psha == row["upstream_head"]:
        row.update(propagation_basis="never_propagated", propagation_tier="UNKNOWN-BASELINE",
                   propagation_tier_reason="never_propagated_no_verified_baseline")
        return
    owner, repo = parse_owner_repo(entry.get("repo_url"))
    cmp_ = fetch_compare(owner, repo, psha, row["upstream_head"], runner=ctx.runner, max_visible=ctx.max_visible)
    row["propagation_basis"] = "propagated_sha"
    if cmp_["error"]:
        kind = cmp_["error"]["kind"]
        if kind in ORPHAN_KINDS:
            row.update(propagation_tier="UNKNOWN", propagation_tier_reason=f"ORPHANED_PROPAGATED_BASELINE:{kind}")
        else:
            row.update(propagation_tier="UNKNOWN", propagation_tier_reason=f"compare_failed:{kind}",
                       propagation_transient=kind in TRANSIENT_KINDS)
        return
    verdict = classify_tier(row["platform"], cmp_, config=ctx.config)
    row.update(propagation_tier=verdict["tier"], propagation_tier_reason=verdict["reason"],
               propagation_ahead_by=cmp_["ahead_by"], propagation_files_seen=cmp_["files_seen"],
               propagation_source_files=verdict["source_files"], propagation_truncated=verdict["truncated"],
               propagation_api_surface_touched=verdict["api_surface_touched"],
               propagation_api_files=verdict["api_files"])


def _release_for(entry: "dict[str, Any]", head: "str | None", ctx: Context) -> "tuple[str, str]":
    family, platform = entry["family"], entry["platform"]
    info = (ctx.registry.get(family) or {}).get(platform)
    probe_result = None
    if ctx.probe and info and info.get("registry_type"):
        ver = info.get("verification") or {}
        try:
            probe_result = publication_probe.probe_publication(
                {"registry_type": info.get("registry_type"), "candidate": info.get("candidate") or {},
                 "published": bool(ver.get("published")), "record_verified_at": ver.get("verified_at")},
                repo_url=entry.get("repo_url"), fetch=ctx.probe_fetch)
        except Exception as exc:  # noqa: BLE001 -- a probe bug must never abort the fleet run
            return "unknown", f"probe_failed:{type(exc).__name__}"
    return compute_release_state(info, head, probe=probe_result)


def analyze_product(entry: "dict[str, Any]", ctx: Context) -> "dict[str, Any]":
    family, platform = entry["family"], entry["platform"]
    key = f"{family}/{platform}"
    owner, repo = parse_owner_repo(entry.get("repo_url"))
    model_exists, model_sha = read_model_sha(family, platform)
    baselines_sha = ctx.baselines.get(key) or None
    baseline_assumed = False
    baseline = model_sha
    if baseline is None and model_exists and baselines_sha:
        baseline, baseline_assumed = baselines_sha, True
    row: dict[str, Any] = {
        "product": key, "family": family, "platform": platform, "repo": f"{owner}/{repo}" if owner else None,
        "knowledge_sha": model_sha, "baselines_sha": baselines_sha, "baseline_assumed": baseline_assumed,
        "baseline_stores_disagree": bool(model_sha and baselines_sha and model_sha != baselines_sha),
        "upstream_head": None, "status": "ok", "tier": "UNKNOWN", "tier_reason": None, "transient": False,
        "compare_status": None, "ahead_by": None, "files_seen": 0, "source_files": 0,
        "api_surface_touched": False, "truncated": False, "api_files": [],
        "release_state": "unknown", "release_state_reason": None,
        "ground_truth_tier": la.ground_truth_tier_for(platform),
    }

    def finish(**kw: Any) -> "dict[str, Any]":
        row.update(kw)
        row["release_state"], row["release_state_reason"] = _release_for(entry, row["upstream_head"], ctx)
        if row["upstream_head"] and row["status"] in ("ok", "orphaned_baseline", "error"):
            _derive_propagation(row, entry, ctx)
        else:
            row["propagation_status"] = cps.compute_status(
                {**(ctx.state_lookup(family, platform) or {}), "upstream_head": row["upstream_head"]})
        return row

    if not owner:
        return finish(status="error", tier_reason="repo_url_unparseable")
    head, err = git_head(entry.get("clone_url") or entry["repo_url"], runner=ctx.runner)
    if head is None:
        if err["kind"] in UNREACHABLE_KINDS:
            # the repository itself cannot be listed: renamed / deleted / no access. Not an orphaned
            # baseline (that needs a reachable repository), and not worth an issue.
            return finish(status="repo_unreachable", tier_reason=f"repo_unreachable:{err['kind']}:{err['message']}")
        return finish(status="error", tier_reason=f"ls_remote_failed:{err['kind']}:{err['message']}",
                      transient=err["kind"] in TRANSIENT_KINDS)
    row["upstream_head"] = head
    if baseline is None:
        reason = "no_knowledge" if not model_exists else "model_has_no_repo_sha"
        return finish(status="no_knowledge", tier_reason=reason)
    if baseline == head:
        return finish(tier="NO_CHANGE", tier_reason="knowledge_equals_upstream_head", compare_status="identical",
                      ahead_by=0)
    max_visible = int((ctx.config.get("truncation") or {}).get("max_files_visible", 300))
    cmp_ = fetch_compare(owner, repo, baseline, head, runner=ctx.runner, max_visible=max_visible)
    if cmp_["error"]:
        kind = cmp_["error"]["kind"]
        if kind in ORPHAN_KINDS:
            return finish(status="orphaned_baseline", tier_reason=f"ORPHANED_BASELINE:{kind}",
                          compare_status="orphaned_baseline")
        return finish(status="error", tier_reason=f"compare_failed:{kind}:{cmp_['error']['message']}",
                      transient=kind in TRANSIENT_KINDS)
    verdict = classify_tier(platform, cmp_, config=ctx.config)
    return finish(tier=verdict["tier"], tier_reason=verdict["reason"], compare_status=cmp_["status"],
                  ahead_by=cmp_["ahead_by"], files_seen=cmp_["files_seen"], source_files=verdict["source_files"],
                  api_surface_touched=verdict["api_surface_touched"], truncated=verdict["truncated"],
                  api_files=verdict["api_files"])


# ── B12: baseline-store health ───────────────────────────────────────────────

def projection_staleness(*, runner: Runner, offline: bool = False) -> "dict[str, Any]":
    """Read-only: `regen_baseline_projections.py check-staleness --json` through the runner."""
    if offline:
        return {"ran": False, "reason": "skipped_offline"}
    res = runner([sys.executable, str(REGEN_SCRIPT), "check-staleness", "--json"], timeout=120)
    out = res.stdout or ""
    lo, hi = out.find("["), out.rfind("]")
    if res.returncode not in (0, 1) or lo == -1 or hi < lo:
        return {"ran": False, "reason": f"check_staleness_failed:{_short(_err_text(res), 120)}"}
    try:
        stale = json.loads(out[lo:hi + 1])
    except json.JSONDecodeError:
        return {"ran": False, "reason": "check_staleness_unparseable"}
    stale = sorted(stale, key=lambda s: (s.get("family", ""), s.get("platform", "")))
    return {"ran": True, "stale_count": len(stale), "stale": stale}


def baseline_stores_summary(rows: "list[dict[str, Any]]", projection: "dict[str, Any] | None") -> "dict[str, Any]":
    return {
        "disagree_count": sum(1 for r in rows if r["baseline_stores_disagree"]),
        "disagree_products": [r["product"] for r in rows if r["baseline_stores_disagree"]],
        "missing_baseline_products": [r["product"] for r in rows if r["knowledge_sha"] and not r["baselines_sha"]],
        "projection_staleness": projection,
    }


# ── report builders ──────────────────────────────────────────────────────────

def _count(rows: "list[dict[str, Any]]", field: str) -> "dict[str, int]":
    out: dict[str, int] = {}
    for r in rows:
        out[r[field]] = out.get(r[field], 0) + 1
    return dict(sorted(out.items()))


def build_ledger(rows: "list[dict[str, Any]]", *, now: str, projection: "dict[str, Any] | None" = None,
                 scope: "list[str] | None" = None) -> "dict[str, Any]":
    rows = sorted(rows, key=lambda r: r["product"])
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "fleet_drift",
        "scope": sorted(scope) if scope else "all_active",
        "products": {r["product"]: r for r in rows},
        "summary": {
            "total": len(rows),
            "by_tier": _count(rows, "tier"),
            "by_status": _count(rows, "status"),
            "by_release_state": _count(rows, "release_state"),
            "drifted": sum(1 for r in rows if r["knowledge_sha"] and r["upstream_head"]
                           and r["knowledge_sha"] != r["upstream_head"]),
            "api_touched": [r["product"] for r in rows if r["tier"] == "API_TOUCHED"],
            "truncated": [r["product"] for r in rows if r["truncated"]],
            "no_knowledge": [r["product"] for r in rows if r["status"] == "no_knowledge"],
            "orphaned_baseline": [r["product"] for r in rows if r["status"] == "orphaned_baseline"],
            "repo_unreachable": [r["product"] for r in rows if r["status"] == "repo_unreachable"],
            "never_propagated": [r["product"] for r in rows if r.get("propagation_basis") == "never_propagated"],
            "errors": [r["product"] for r in rows if r["status"] == "error"],
        },
        "baseline_stores": baseline_stores_summary(rows, projection),
        "volatile": {"generated_at": now},
    }


def render_markdown(ledger: "dict[str, Any]") -> str:
    s = ledger["summary"]
    lines = [
        "# Fleet drift ledger", "",
        f"Products: {s['total']} | drifted: {s['drifted']} | API touched: {len(s['api_touched'])} | "
        f"no knowledge: {len(s['no_knowledge'])} | orphaned baseline: {len(s['orphaned_baseline'])} | "
        f"repo_unreachable: {len(s['repo_unreachable'])} | never propagated: {len(s['never_propagated'])} | "
        f"errors: {len(s['errors'])}", "",
        "Tiers: " + ", ".join(f"{k}={v}" for k, v in s["by_tier"].items()),
        "", "Release state: " + ", ".join(f"{k}={v}" for k, v in s["by_release_state"].items()), "",
        "| Product | Tier | Reason | Ahead | Files | Src | API | Trunc | Release | GT | Propagation | Stores disagree |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for key, r in ledger["products"].items():
        lines.append("| {p} | {t} | {why} | {a} | {f} | {s} | {api} | {tr} | {rel} | {gt} | {prop} | {dis} |".format(
            p=key, t=r["tier"], why=r["tier_reason"] or "", a="" if r["ahead_by"] is None else r["ahead_by"],
            f=r["files_seen"], s=r["source_files"], api="yes" if r["api_surface_touched"] else "no",
            tr="yes" if r["truncated"] else "no", rel=r["release_state"], gt=r["ground_truth_tier"],
            prop=r.get("propagation_status", ""), dis="yes" if r["baseline_stores_disagree"] else "no"))
    b = ledger["baseline_stores"]
    lines += ["", "## Baseline stores (model.yaml vs data/upstream_baselines.json)", "",
              f"Disagree: {b['disagree_count']}" + (f" ({', '.join(b['disagree_products'])})" if b["disagree_products"] else ""),
              f"Missing in baselines store: {len(b['missing_baseline_products'])}"]
    p = b.get("projection_staleness")
    if p:
        lines.append("Projection staleness: " + (f"{p['stale_count']} stale" if p.get("ran") else f"not run ({p.get('reason')})"))
    if s["repo_unreachable"]:
        lines += ["", "## repo_unreachable (renamed / deleted / no access -- needs a human, no issue filed)", ""]
        lines += [f"- {k}: {ledger['products'][k]['tier_reason']}" for k in s["repo_unreachable"]]
    lines += ["", f"_Generated at {ledger['volatile']['generated_at']} (volatile)._", ""]
    return "\n".join(lines)


def build_sweep_report(rows: "list[dict[str, Any]]", *, now: str) -> "dict[str, Any]":
    """repo_patrol sweep_report.json schema (generated_at, total_products, changed, unchanged,
    fetch_failures, summary) so /discovery-triage can consume it. Impact mapping follows
    repo_patrol._classify_impact: source/API change or no stored sha -> HIGH, non-source -> LOW,
    cannot determine -> MEDIUM. Extra keys (tier, ...) are additive."""
    changed, unchanged, failures = [], [], []
    for r in sorted(rows, key=lambda r: r["product"]):
        base = {"family": r["family"], "platform": r["platform"]}
        if r["upstream_head"] is None:
            failures.append({**base, "error": r["tier_reason"] or "upstream head unavailable"})
        elif r["tier"] == "NO_CHANGE":
            unchanged.append({**base, "sha": r["upstream_head"]})
        else:
            impact = {"API_TOUCHED": "HIGH", "SOURCE": "HIGH", "NON_SOURCE": "LOW"}.get(r["tier"], "MEDIUM")
            if r["status"] == "no_knowledge":
                impact = "HIGH"
            changed.append({**base, "stored_sha": r["knowledge_sha"], "current_sha": r["upstream_head"],
                            "impact": impact, "tier": r["tier"], "tier_reason": r["tier_reason"],
                            "api_surface_touched": r["api_surface_touched"], "release_state": r["release_state"]})
    return {
        "generated_at": now, "total_products": len(rows), "changed": changed, "unchanged": unchanged,
        "fetch_failures": failures,
        "summary": {
            "changed": len(changed), "unchanged": len(unchanged), "fetch_failures": len(failures),
            "high_impact": sum(1 for c in changed if c["impact"] == "HIGH"),
            "medium_impact": sum(1 for c in changed if c["impact"] == "MEDIUM"),
            "low_impact": sum(1 for c in changed if c["impact"] == "LOW"),
        },
    }


def _write_text(path: "Path | str", text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


# ── issues ───────────────────────────────────────────────────────────────────

class IssueLookupError(Exception):
    pass


def issue_prefix(family: str, platform: str) -> str:
    return f"{ISSUE_PREFIX}-{family}-{platform}"


def issue_title(family: str, platform: str) -> str:
    return f"{issue_prefix(family, platform)}: propagate upstream changes to content"


def prospective_status(row: "dict[str, Any]", state_lookup: Callable[[str, str], "dict | None"]) -> str:
    rec = dict(state_lookup(row["family"], row["platform"]) or {})
    rec["upstream_head"] = row["upstream_head"]
    return cps.compute_status(rec)


def effective_tier(row: "dict[str, Any]") -> str:
    """The tier that ranks the work. A since-propagation tier wins when one was derived from a verified
    propagated sha. A never-propagated product keeps its knowledge-drift tier when that already shows
    real drift (API_TOUCHED / SOURCE / UNKNOWN); only a quiet one (NO_CHANGE / NON_SOURCE) ranks as
    UNKNOWN-BASELINE, i.e. last."""
    if is_never_propagated(row):
        return row["tier"] if row["tier"] in ("API_TOUCHED", "SOURCE", "UNKNOWN") else "UNKNOWN-BASELINE"
    return row.get("propagation_tier") or row["tier"]


def is_never_propagated(row: "dict[str, Any]") -> bool:
    return row.get("propagation_basis") == "never_propagated"


def issue_body(row: "dict[str, Any]", prop_status: str, rec: "dict | None") -> str:
    """Stable part first (tier, release state, instructions), then VOLATILE_MARKER and the facts
    that change on every upstream commit (HEAD / knowledge / propagated sha, ahead_by, counts, file
    list). Only the stable part counts when deciding whether an open issue is stale."""
    f, p = row["family"], row["platform"]
    ptier = row.get("propagation_tier")
    since_propagation = bool(ptier) and not is_never_propagated(row)
    lines = [f"<!-- fleet-propagate:{f}/{p} -->"]
    if is_never_propagated(row):
        lines.append(f"<!-- fleet-propagate:label {NEVER_PROPAGATED_LABEL} -->")
    lines += [
        f"## Upstream changes need content propagation: {f}/{p}", "",
        f"- **Propagation status**: {prop_status}",
        f"- **Tier since knowledge baseline**: {row['tier']} ({row['tier_reason']})",
    ]
    if is_never_propagated(row):
        lines.append(f"- **Tier since last propagation**: {ptier} -- never propagated: content has no verified "
                     f"propagation baseline, so there is nothing to diff against; treat the whole surface as unreconciled")
    elif ptier:
        lines.append(f"- **Tier since last propagation**: {ptier} ({row.get('propagation_tier_reason')})")
    touched = row.get("propagation_api_surface_touched", row["api_surface_touched"]) if since_propagation else row["api_surface_touched"]
    truncated = row.get("propagation_truncated", row["truncated"]) if since_propagation else row["truncated"]
    lines += [
        f"- **API surface touched**: {'yes' if touched else 'no'}"
        + (" (compare truncated: more files exist than were visible)" if truncated else ""),
        f"- **Release state**: {row['release_state']} ({row['release_state_reason']})",
        *(["- **unreleased main: do not present as released.** These changes are on the default branch "
           "but not in a published release; propagate them with an availability qualifier."]
          if row["release_state"] == "unreleased_main" else []),
        f"- **Ground truth**: {row['ground_truth_tier']}"
        + (" (file-level evidence only, not compiled-API truth)" if row["ground_truth_tier"] == "GT-2" else ""),
        "",
        "### Next step",
        f"Run `/knowledge-update {f} {p}`, then propagate the change to reference/docs/kb/blog/products "
        f"and record it through the capability-surface gate. This issue closes automatically once the "
        f"product's propagation state is PROPAGATED (pushed) at upstream HEAD.",
        "", "_One issue per product; the section below the marker changes on every scan and is ignored when "
        "deciding whether this issue is stale._",
        "", VOLATILE_MARKER, "",
        f"- Upstream HEAD: `{row['upstream_head']}`",
        f"- Knowledge baseline: `{row['knowledge_sha'] or 'none'}`",
        f"- Content propagated at: `{(rec or {}).get('content_propagated_sha') or 'never'}`",
        f"- Ahead by: {row['ahead_by'] if row['ahead_by'] is not None else 'unknown'} commit(s), "
        f"{row['files_seen']} file(s) seen, {row['source_files']} source",
    ]
    api_files = (row.get("propagation_api_files") if since_propagation else None) or row["api_files"]
    if api_files:
        lines += ["", "API-path files changed (first %d):" % len(api_files)] + [f"- `{x}`" for x in api_files]
    return "\n".join(lines)


def stable_body(body: "str | None") -> str:
    """The part of an issue body that decides staleness: CRLF -> LF, everything after the volatile
    marker dropped, surrounding whitespace stripped."""
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    return text.split(VOLATILE_MARKER, 1)[0].strip()


def decide_issue_action(row: "dict[str, Any]", prop_status: str) -> "tuple[str, str]":
    """('close'|'skip'|'file', reason). Only PROPAGATED closes: PROPAGATED_LOCAL means the content is
    not pushed yet, DRIFTED / UNRECORDED mean the work is still owed."""
    if prop_status == "PROPAGATED":
        return "close", "propagation_state_matches_upstream_head"
    if prop_status == "PROPAGATED_LOCAL":
        return "skip", "propagated_local_awaiting_push"
    if row["upstream_head"] is None:
        return "skip", "no_upstream_head"
    if row["status"] == "repo_unreachable":
        return "skip", "repo_unreachable"
    if row["status"] == "no_knowledge":
        return "skip", "no_knowledge"
    if row["transient"] or row.get("propagation_transient"):
        return "skip", "transient_error"
    if row.get("propagation_tier") in ("NO_CHANGE", "NON_SOURCE"):
        return "skip", "no_source_drift_since_propagation"
    # Not skipped on the KNOWLEDGE tier alone: a knowledge-only refresh makes tier NO_CHANGE while no
    # page was ever reconciled (UNKNOWN-BASELINE). unreleased_main is not a reason to skip either:
    # the work item is needed so content is propagated with availability qualifiers.
    return "file", "needs_propagation"


class IssueClient:
    """`gh`-backed issue operations through an injected runner. One list call per run (the REST
    list endpoint, not the lagging search index) caches the open FLEET-PROPAGATE issues. A list that
    reaches ISSUE_LIST_LIMIT may be truncated: that is an error (a miss would create duplicates)."""

    def __init__(self, *, repo: str, runner: Runner):
        self.repo, self.runner = repo, runner
        self._open: "list[dict] | None" = None
        self._error: "IssueLookupError | None" = None
        self._label_ready = False

    def _list(self) -> "list[dict]":
        if self._error is not None:
            raise self._error
        if self._open is None:
            try:
                self._open = self._fetch()
            except IssueLookupError as exc:
                self._error = exc
                raise
        return self._open

    def _fetch(self) -> "list[dict]":
        res = self.runner(["gh", "issue", "list", "--repo", self.repo, "--state", "open",
                           "--json", "number,title,body,updatedAt", "--limit", str(ISSUE_LIST_LIMIT)], timeout=120)
        if res.returncode != 0:
            raise IssueLookupError(_short(_err_text(res)))
        try:
            items = json.loads(res.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise IssueLookupError("unparseable gh issue list output") from exc
        if len(items) >= ISSUE_LIST_LIMIT:
            raise IssueLookupError(
                f"gh issue list returned {len(items)} open issues, reaching its limit of {ISSUE_LIST_LIMIT}: "
                f"the list may be truncated, so existing FLEET-PROPAGATE issues cannot be ruled out "
                f"(refusing to risk duplicates)")
        return [i for i in items if str(i.get("title", "")).startswith(ISSUE_PREFIX + "-")]

    def find(self, family: str, platform: str) -> "dict | None":
        """The OLDEST (lowest-numbered) open issue for this product, whatever the list order."""
        prefix = issue_prefix(family, platform)
        hits = [i for i in self._list() if i["title"] == prefix or i["title"].startswith(prefix + ":")]
        return min(hits, key=lambda i: i["number"]) if hits else None

    def ensure_label(self, name: str) -> None:
        if not self._label_ready:
            self.runner(["gh", "label", "create", name, "--repo", self.repo, "--color", "d93f0b"], timeout=60)
            self._label_ready = True    # rc ignored: "already exists" is the normal outcome after run one

    def create(self, title: str, body: str, *, labels: "list[str] | None" = None) -> "int | None":
        cmd = ["gh", "issue", "create", "--repo", self.repo, "--title", title, "--body", body]
        for label in labels or []:
            self.ensure_label(label)
            cmd += ["--label", label]
        res = self.runner(cmd, timeout=60)
        if res.returncode != 0:
            raise RuntimeError(_short(_err_text(res)))
        tail = (res.stdout or "").strip().rsplit("/", 1)[-1]
        number = int(tail) if tail.isdigit() else None
        if number is not None:
            self._list().append({"number": number, "title": title, "body": body})
        return number

    def edit(self, number: int, title: str, body: str, *, add_labels: "list[str] | None" = None,
             remove_labels: "list[str] | None" = None) -> None:
        cmd = ["gh", "issue", "edit", str(number), "--repo", self.repo, "--title", title, "--body", body]
        for label in add_labels or []:
            self.ensure_label(label)
            cmd += ["--add-label", label]
        for label in remove_labels or []:
            cmd += ["--remove-label", label]
        res = self.runner(cmd, timeout=60)
        if res.returncode != 0:
            raise RuntimeError(_short(_err_text(res)))

    def close(self, number: int, comment: str) -> None:
        res = self.runner(["gh", "issue", "close", str(number), "--repo", self.repo, "--comment", comment], timeout=60)
        if res.returncode != 0:
            raise RuntimeError(_short(_err_text(res)))


_TIER_RANK = {"API_TOUCHED": 0, "SOURCE": 1, "UNKNOWN": 2, "UNKNOWN-BASELINE": 3}


def _has_label_marker(body: "str | None") -> bool:
    return f"fleet-propagate:label {NEVER_PROPAGATED_LABEL}" in (body or "")


def process_issues(rows: "list[dict[str, Any]]", *, client: "IssueClient | None", max_issues: int,
                   state_lookup: Callable[[str, str], "dict | None"], dry_run: bool,
                   max_edits: "int | None" = None) -> "list[dict[str, Any]]":
    """Plan (dry_run / client None) or execute the issue operations.

    Order and budgets (so a pile of stale issues can never starve new products):
      1. closes                      -- unbudgeted (they reduce noise);
      2. creates, ranked             -- budget max_issues; API_TOUCHED, SOURCE, UNKNOWN, then
                                        UNKNOWN-BASELINE (never propagated), then product key;
      3. edits, oldest-updated first -- SEPARATE budget max_edits (default: max_issues). Editing
                                        refreshes updatedAt, so the next run rotates to the next
                                        oldest. An issue whose STABLE body is unchanged costs nothing.
    """
    max_edits = max_issues if max_edits is None else max_edits
    results: dict[str, dict[str, Any]] = {}
    plan = []
    for r in rows:
        prop = r["propagation_status"] = prospective_status(r, state_lookup)
        action, reason = decide_issue_action(r, prop)
        res = {"product": r["product"], "action": action, "reason": reason, "issue_number": None}
        results[r["product"]] = res
        if action == "skip":
            res["action"] = "skipped"
        elif dry_run or client is None:
            res["action"] = "would_close" if action == "close" else "would_file"
        else:
            plan.append((_TIER_RANK.get(effective_tier(r), 4), r["product"], r, prop, action))
    plan.sort(key=lambda t: (t[0], t[1]))

    edits: list[tuple] = []
    creates_left = max(0, max_issues)
    for _rank, key, r, prop, action in plan:
        res = results[key]
        rec = state_lookup(r["family"], r["platform"])
        try:
            existing = client.find(r["family"], r["platform"])
            if action == "close":
                if existing is None:
                    res["action"], res["reason"] = "skipped", "no_open_issue"
                else:
                    client.close(existing["number"], f"Propagation state now matches upstream HEAD `{r['upstream_head']}`.")
                    res.update(action="closed", issue_number=existing["number"])
                continue
            title, body = issue_title(r["family"], r["platform"]), issue_body(r, prop, rec)
            labels = [NEVER_PROPAGATED_LABEL] if is_never_propagated(r) else []
            if existing is None:
                if creates_left <= 0:
                    res.update(action="deferred", reason="max_issues_per_run")
                    continue
                res.update(action="created", issue_number=client.create(title, body, labels=labels))
                creates_left -= 1
                continue
            res["issue_number"] = existing["number"]
            if stable_body(existing.get("body")) == stable_body(body) and existing["title"] == title:
                res["action"] = "unchanged"
                continue
            add = labels if labels and not _has_label_marker(existing.get("body")) else []
            remove = [NEVER_PROPAGATED_LABEL] if not labels and _has_label_marker(existing.get("body")) else []
            edits.append((existing.get("updatedAt") or "", key, existing, title, body, add, remove))
        except (IssueLookupError, RuntimeError) as exc:
            res.update(action="failed", reason=str(exc))
    edits_left = max(0, max_edits)
    for _updated, key, existing, title, body, add, remove in sorted(edits, key=lambda e: (e[0], e[1])):
        res = results[key]
        if edits_left <= 0:
            res.update(action="deferred", reason="max_edits_per_run")
            continue
        try:
            client.edit(existing["number"], title, body, add_labels=add, remove_labels=remove)
            res.update(action="updated")
            edits_left -= 1
        except RuntimeError as exc:
            res.update(action="failed", reason=str(exc))
    return sorted(results.values(), key=lambda x: x["product"])


# ── state writes ─────────────────────────────────────────────────────────────

def update_state(rows: "list[dict[str, Any]]", *, now: str, issues: "dict[str, int | None] | None" = None) -> "list[str]":
    """record_drift for every row with a known upstream head. Returns the skipped products."""
    skipped = []
    for r in rows:
        if r["upstream_head"] is None:
            skipped.append(r["product"])
            continue
        extra = {"last_issue_number": issues[r["product"]]} if issues and issues.get(r["product"]) else None
        (_cfg_record_drift or cps.record_drift)(
            r["family"], r["platform"], upstream_head=r["upstream_head"], knowledge_sha=r["knowledge_sha"],
            tier=r["tier"], release_state=r["release_state"], ahead_by=r["ahead_by"], files_seen=r["files_seen"],
            source_files=r["source_files"], api_surface_touched=r["api_surface_touched"], truncated=r["truncated"],
            ground_truth_tier=r["ground_truth_tier"], baseline_assumed=r["baseline_assumed"], observed_at=now,
            tier_reason=r["tier_reason"], release_state_reason=r["release_state_reason"], volatile_extra=extra)
    return skipped


# ── orchestration ────────────────────────────────────────────────────────────

def run_fleet(products: "list[dict[str, Any]]", ctx: Context, *, workers: int = 4) -> "list[dict[str, Any]]":
    if workers > 1 and len(products) > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(lambda e: analyze_product(e, ctx), products))
    return [analyze_product(e, ctx) for e in products]


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="fleet_drift.py", description="Clone-free fleet drift classifier")
    ap.add_argument("--products", nargs="+", metavar="F/P", help="limit to these family/platform products")
    ap.add_argument("--json-out", metavar="PATH", help="write the deterministic ledger JSON")
    ap.add_argument("--md-out", metavar="PATH", help="write the Markdown ledger")
    ap.add_argument("--sweep-out", metavar="PATH", help="write a repo_patrol sweep_report.json-compatible file")
    ap.add_argument("--update-state", action="store_true", help="write drift fields via content_propagation_state.record_drift")
    ap.add_argument("--file-issues", action="store_true", help="file/update/close one FLEET-PROPAGATE issue per product")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"), metavar="OWNER/REPO",
                    help="repository that receives the issues (default: $GITHUB_REPOSITORY; required to file)")
    ap.add_argument("--max-issues-per-run", type=int, default=10, metavar="N",
                    help="budget for NEW issues per run (creates are budgeted first)")
    ap.add_argument("--max-edits-per-run", type=int, default=None, metavar="N",
                    help="separate budget for edits of existing issues, oldest-updated first (default: same as --max-issues-per-run)")
    ap.add_argument("--state-file", metavar="PATH",
                    help="use this content_propagation_state.json instead of data/ (required for --offline --update-state)")
    ap.add_argument("--release-trigger", metavar="F/P",
                    help="refresh ONE product's release_state from the (already updated) registry, update its state, file/update its issue")
    ap.add_argument("--offline", metavar="FIXTURES_DIR", help="use recorded responses; never writes issues")
    ap.add_argument("--dry-run", action="store_true", help="no state writes, no issue operations (reports still written when requested)")
    ap.add_argument("--probe-registry", action="store_true", help="live-probe the package registry for release_state")
    ap.add_argument("--check-projections", action="store_true", help="include regen_baseline_projections check-staleness --json")
    ap.add_argument("--workers", type=int, default=4, metavar="N")
    return ap


def main(argv: "list[str] | None" = None, *, runner: "Runner | None" = None, fetch: "Callable | None" = None,
         now: "str | None" = None, out=None) -> int:
    args = build_parser().parse_args(argv)
    previous_state_path = cps.state_path()
    if args.state_file:
        cps.configure(args.state_file)
    try:
        return _run(args, runner=runner, fetch=fetch, now=now, out=out or sys.stdout)
    finally:
        if args.state_file:
            cps.configure(previous_state_path)


STATE_ERRORS = (cps.StateCorrupt, cps.StateWriteError, cps.StateLockTimeout, cps.StateReadError)


def _run(args: argparse.Namespace, *, runner: "Runner | None", fetch: "Callable | None", now: "str | None", out) -> int:
    now = now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    offline = bool(args.offline)
    dry = bool(args.dry_run or offline)
    # A write to the state file must be a REAL run: never --dry-run, and never --offline (recorded
    # fixtures must not be able to flip the real state) unless --state-file points somewhere explicit.
    write_state = bool(args.update_state or args.release_trigger) and not args.dry_run and (not offline or bool(args.state_file))
    selected = args.products
    if args.release_trigger:
        selected = [args.release_trigger]
        args.file_issues = True
    try:
        products = load_active_products(selected)
        config = la.load_language_config()
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.file_issues and not dry and not args.repo:
        print("ERROR: --repo OWNER/REPO (or $GITHUB_REPOSITORY) is required to file issues", file=sys.stderr)
        return 2
    runner = FixtureRunner(args.offline) if offline else (runner or la.default_runner)
    ctx = Context(runner=runner, config=config, baselines=_read_json(BASELINES_PATH, {}),
                  registry=_read_json(REGISTRY_PATH, {}), probe_fetch=fetch,
                  probe=bool(args.probe_registry and not offline), state_lookup=cps.read_state)

    issue_results: list[dict[str, Any]] = []
    try:
        rows = run_fleet(products, ctx, workers=max(1, args.workers))
        projection = projection_staleness(runner=runner, offline=offline) if args.check_projections else None
        if args.file_issues:
            client = None if dry else IssueClient(repo=args.repo, runner=runner)
            issue_results = process_issues(rows, client=client, max_issues=args.max_issues_per_run,
                                           max_edits=args.max_edits_per_run, state_lookup=cps.read_state, dry_run=dry)
        for r in rows:
            r.setdefault("propagation_status", prospective_status(r, cps.read_state))
    except STATE_ERRORS as exc:
        print(f"ERROR: cannot read the propagation state ({type(exc).__name__}): {exc}", file=sys.stderr)
        return EXIT_STATE
    issue_numbers = {x["product"]: x["issue_number"] for x in issue_results if x["issue_number"]}

    # reports first: a state-write failure below must never cost the operator the findings
    ledger = build_ledger(rows, now=now, projection=projection, scope=selected)
    if args.json_out:
        _write_text(args.json_out, dumps(ledger))
    if args.md_out:
        _write_text(args.md_out, render_markdown(ledger))
    if args.sweep_out:
        _write_text(args.sweep_out, dumps(build_sweep_report(rows, now=now)))

    s = ledger["summary"]
    print(f"fleet_drift: {s['total']} products | tiers {s['by_tier']} | release {s['by_release_state']} | "
          f"stores_disagree={ledger['baseline_stores']['disagree_count']}", file=out)
    for key, r in ledger["products"].items():
        if r["tier"] != "NO_CHANGE" or r["status"] != "ok":
            print(f"  {key:<24} {r['tier']:<11} api={'Y' if r['api_surface_touched'] else 'n'} "
                  f"trunc={'Y' if r['truncated'] else 'n'} release={r['release_state']:<15} "
                  f"{r['status'] if r['status'] != 'ok' else ''} {r['tier_reason']}", file=out)
    if s["repo_unreachable"]:
        print(f"  repo_unreachable (no issue filed): {', '.join(s['repo_unreachable'])}", file=out)
    for res in issue_results:
        if res["action"] != "skipped":
            print(f"  issue {res['product']}: {res['action']}"
                  + (f" #{res['issue_number']}" if res["issue_number"] else "") + f" ({res['reason']})", file=out)
    if args.update_state and offline and not args.state_file and not args.dry_run:
        print("  state NOT written: --offline never touches the real state file (pass --state-file PATH to record elsewhere)", file=out)

    if write_state:
        try:
            skipped_state = update_state(rows, now=now, issues=issue_numbers)
        except STATE_ERRORS as exc:
            print(f"ERROR: the state file was not updated ({type(exc).__name__}): {exc}. Reports are written and "
                  f"issue operations above already happened; each product record is written atomically, so the file is never half-written.", file=sys.stderr)
            return EXIT_STATE
        if skipped_state:
            print(f"  state not updated (no upstream head): {', '.join(skipped_state)}", file=out)
    return 1 if any(x["action"] == "failed" for x in issue_results) else 0


if __name__ == "__main__":
    sys.exit(main())
