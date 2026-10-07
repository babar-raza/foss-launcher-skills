"""skill_provenance_audit.py -- post-hoc "skills-only" audit of a commit range.

Mission MT074, card A11 (AC-5 enforcement, plan section "Skill-first matrix").

WHY THIS EXISTS
---------------
PreToolUse hooks only gate Edit/Write, and ``skill_context begin`` accepts any
skill ID, so nothing at write time proves that a changed file was produced
under a skill that is SANCTIONED to write that kind of file. This audit is the
post-hoc enforcement: for every commit in ``BASE..HEAD`` it

  1. maps each changed file to a FILE CLASS (ordered globs, first match wins);
  2. looks up the skills sanctioned to write that class;
  3. finds the skills the commit declares: skill-run records in
     ``reports/skill-runs/*.json`` whose ``commit_sha`` matches (retroactive
     records included; several records for one sha are unioned); only if NO
     usable record exists, the ``Skills invoked:`` commit-message trailer;
  4. requires, for EVERY non-exempt class touched, at least one declared skill
     that is sanctioned for that class (or, for classes with
     ``allow_gap_markers``, a declared gap marker such as ``GAP-APPROVED``).

Verdicts per commit:
  PASS       every touched non-exempt class is covered (or the commit only
             touches exempt classes / is a merge commit / changes no files)
  VIOLATION  a declaration exists but some touched class has no sanctioned skill
  GAP        a declaration exists and every sanctioned-skill class is covered,
             but a touched ``no_skill`` class (no registered skill writes it) is
             not covered by a resolvable gap marker
  NO_RECORD  the commit touches non-exempt classes and has neither a usable
             record nor a trailer

``--fail-on-violation`` fails on VIOLATION, GAP and NO_RECORD. Files that match no
class use the matrix ``default`` class (exempt, WARN) but are counted in the summary
as ``unclassified_files`` / ``unclassified_commits`` so they cannot hide.

GAP MARKERS
-----------
A declared token ``<NAME>:<id>`` (NAME from the matrix ``gap_markers``, e.g. the
gap-approved marker) stands in for a sanctioned skill on classes with
``allow_gap_markers: true`` and on every ``no_skill`` class, but only when ``<id>``
resolves under the matrix ``gap_dir``: an ``entries[].id`` row of ``index.yaml`` or a
report file whose stem equals ``<id>``. A bare ``<NAME>`` (reason "gap marker without
id") or an unknown id (reason "gap id not found: <id>") never counts.

KNOWN LIMITS (also stated in every report header)
-------------------------------------------------
* ``reports/skill-runs/*.json`` is gitignored: the audit is only valid on the machine
  that holds the records. Reports say ``records_source: local-gitignored`` and
  ``records_read: N``. A clone without the records reports NO_RECORD / trailer-only.
* Records are plain local files and are not tamper-proof; a "Skills invoked:" trailer
  is a claim, not proof that the skill ran.

THE MATRIX (data, not code -- see scripts/pipeline/config/skill_file_class_matrix.yaml)
----------------------------------------------------------------------------------
::

    version: 1                      # required, must be 1
    gap_markers: [<NAME>...]        # optional; marker names, see GAP MARKERS
    gap_dir: <repo-relative dir>    # optional; where marker ids resolve
    default:                        # optional; class for files matching nothing
      id: <str>                     #   default id "unclassified"
      exempt: true|false            #   default true
      warn: true|false              #   default true (emit a WARN note per commit)
      skills: [<skill id>...]       #   required when exempt is false
    classes:                        # required, non-empty, ORDER = priority
      - id: <str>                   # required, unique
        patterns: [<glob>...]       # required, non-empty. '*' = no '/', '?' = one
                                    #   non-'/' char, '**' = anything incl. '/',
                                    #   '**/' = zero or more directories
        skills: [<skill id>...]     # required unless exempt: true or no_skill: true
        exempt: true|false          # optional, default false
        no_skill: true|false        # optional; no registered skill writes this class
                                    #   (no skills/exempt allowed): reports GAP
        description: <str>          # optional
        allow_gap_markers: bool     # optional, accept a resolvable gap marker
        token_required: bool        # optional, informational note only (never fails)

Unknown keys are rejected so typos cannot silently weaken the audit.

DECLARED SKILLS
---------------
Record skills reuse ``check_skill_run_records._compute_declared_from_record``
and trailer parsing reuses ``check_skill_run_records._parse_declared_skills``
(no duplicated parsing). Records whose ``outcome`` is failure/abandoned do not
back a commit.

SEAMS
-----
``configure(repo_root=..., git_reader=..., record_reader=...)`` sets module
defaults; ``audit_range(...)`` also takes them explicitly. A git reader is any
object with ``commits(base, head) -> list[CommitInfo]`` and
``changed_files(sha) -> list[str]``; a record reader is a callable
``(records_dir) -> list[dict]``; a gap resolver is ``(gap_id) -> bool``
(``build_gap_resolver(dir)`` is the default).

CLI
---
    skill_provenance_audit.py --base REV --head REV [--matrix PATH]
        [--records-dir reports/skill-runs] [--json-out PATH] [--md-out PATH]
        [--fail-on-violation]

Exit 0 normally; 1 with --fail-on-violation when any VIOLATION/GAP/NO_RECORD;
2 on usage/matrix/git errors.

LIMITATIONS: merge commits are not diffed (their content is audited through
the constituent commits in the range); a pathless "Skills invoked:" trailer
cannot prove the skill actually ran; ``token_required`` is informational.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

_OPS_DIR = Path(__file__).resolve().parent
_PIPELINE_ROOT = _OPS_DIR.parents[1]
_REPO_ROOT_DEFAULT = _PIPELINE_ROOT.parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_CI_CHECKS_DIR = str(_REPO_ROOT_DEFAULT / "scripts" / "ci" / "checks")
if _CI_CHECKS_DIR not in sys.path:
    sys.path.append(_CI_CHECKS_DIR)

import yaml  # noqa: E402
import check_skill_run_records as _csr  # noqa: E402

DEFAULT_MATRIX = _PIPELINE_ROOT / "config" / "skill_file_class_matrix.yaml"
DEFAULT_RECORDS_DIR = Path("reports") / "skill-runs"

VERDICT_PASS = "PASS"
VERDICT_VIOLATION = "VIOLATION"
VERDICT_NO_RECORD = "NO_RECORD"
VERDICT_GAP = "GAP"
RECORDS_SOURCE_LOCAL = "local-gitignored"
RECORDS_SOURCE_INJECTED = "injected"
CAVEATS = (
    "reports/skill-runs is gitignored: this audit is only valid on the machine holding the records",
    "records and trailers are not tamper-proof: they are claims, not proof the skill ran",
)

# Records with these outcomes never back a commit.
_UNUSABLE_OUTCOMES = frozenset({"failure", "failed", "abandoned", "aborted"})
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)+(?::[A-Za-z0-9_.\-/]+)?")
_GAP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")

_CLASS_KEYS = {"id", "patterns", "skills", "exempt", "description",
               "allow_gap_markers", "token_required", "no_skill"}
_DEFAULT_KEYS = {"id", "exempt", "warn", "skills", "description"}
_TOP_KEYS = {"version", "gap_markers", "gap_dir", "default", "classes"}


class MatrixError(ValueError):
    """The file-class matrix is missing or invalid."""


# --------------------------------------------------------------------------- #
# Matrix
# --------------------------------------------------------------------------- #

def _glob_to_regex(pattern: str) -> "re.Pattern[str]":
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if pattern.startswith("**", i):
                if pattern.startswith("**/", i):
                    out.append("(?:.*/)?")
                    i += 3
                else:
                    out.append(".*")
                    i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


@dataclass(frozen=True)
class FileClass:
    id: str
    patterns: tuple[str, ...]
    skills: frozenset[str]
    exempt: bool = False
    warn: bool = False
    allow_gap_markers: bool = False
    token_required: bool = False
    no_skill: bool = False
    description: str = ""
    _regexes: tuple = field(default=(), repr=False, compare=False)

    def matches(self, path: str) -> bool:
        return any(rx.match(path) for rx in self._regexes)


@dataclass(frozen=True)
class Matrix:
    classes: tuple[FileClass, ...]
    default: FileClass
    gap_markers: tuple[str, ...] = ()
    gap_dir: str = ""
    source: str = ""

    def classify(self, path: str) -> FileClass:
        p = path.replace("\\", "/")
        while p.startswith("./"):
            p = p[2:]
        for cls in self.classes:
            if cls.matches(p):
                return cls
        return self.default

    def marker_name(self, token: str) -> str | None:
        """The configured marker name ``token`` uses (bare or ``NAME:id``), else None."""
        for name in self.gap_markers:
            if token == name or token.startswith(name + ":"):
                return name
        return None


def _str_list(value, where: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise MatrixError(f"{where}: must be a list of non-empty strings")
    if not value and not allow_empty:
        raise MatrixError(f"{where}: must not be empty")
    return [v.strip() for v in value]


def _bool(value, where: str) -> bool:
    if not isinstance(value, bool):
        raise MatrixError(f"{where}: must be true or false, got {value!r}")
    return value


def _build_class(raw, where: str, *, is_default: bool) -> FileClass:
    if not isinstance(raw, dict):
        raise MatrixError(f"{where}: must be a mapping")
    allowed = _DEFAULT_KEYS if is_default else _CLASS_KEYS
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise MatrixError(f"{where}: unknown key(s) {unknown}; allowed: {sorted(allowed)}")
    cid = raw.get("id", "unclassified" if is_default else None)
    if not isinstance(cid, str) or not cid.strip():
        raise MatrixError(f"{where}: 'id' is required and must be a non-empty string")
    exempt = _bool(raw.get("exempt", True if is_default else False), f"{where}.exempt")
    warn = _bool(raw.get("warn", True), f"{where}.warn") if is_default else False
    patterns: list[str] = []
    if not is_default:
        if "patterns" not in raw:
            raise MatrixError(f"{where} ({cid}): 'patterns' is required")
        patterns = _str_list(raw["patterns"], f"{where} ({cid}).patterns")
    no_skill = _bool(raw.get("no_skill", False), f"{where} ({cid}).no_skill")
    skills: list[str] = []
    if "skills" in raw:
        skills = _str_list(raw["skills"], f"{where} ({cid}).skills", allow_empty=exempt or no_skill)
    if no_skill and (skills or exempt):
        raise MatrixError(f"{where} ({cid}): no_skill classes cannot also declare 'skills' or 'exempt'")
    if not exempt and not no_skill and not skills:
        raise MatrixError(f"{where} ({cid}): non-exempt class needs a non-empty 'skills' list "
                          f"(or no_skill: true)")
    regexes = tuple(_glob_to_regex(p) for p in patterns)
    return FileClass(
        id=cid.strip(), patterns=tuple(patterns), skills=frozenset(skills), exempt=exempt,
        warn=warn,
        allow_gap_markers=_bool(raw.get("allow_gap_markers", False), f"{where} ({cid}).allow_gap_markers"),
        token_required=_bool(raw.get("token_required", False), f"{where} ({cid}).token_required"),
        no_skill=no_skill,
        description=str(raw.get("description", "")), _regexes=regexes,
    )


def parse_matrix(data, source: str = "<memory>") -> Matrix:
    """Validate parsed YAML ``data`` and build a Matrix (raises MatrixError)."""
    if not isinstance(data, dict):
        raise MatrixError(f"{source}: top level must be a mapping")
    unknown = sorted(set(data) - _TOP_KEYS)
    if unknown:
        raise MatrixError(f"{source}: unknown top-level key(s) {unknown}; allowed: {sorted(_TOP_KEYS)}")
    if data.get("version") != 1:
        raise MatrixError(f"{source}: 'version' must be 1, got {data.get('version')!r}")
    raw_classes = data.get("classes")
    if not isinstance(raw_classes, list) or not raw_classes:
        raise MatrixError(f"{source}: 'classes' must be a non-empty list")
    classes: list[FileClass] = []
    seen: set[str] = set()
    for idx, raw in enumerate(raw_classes):
        cls = _build_class(raw, f"{source}: classes[{idx}]", is_default=False)
        if cls.id in seen:
            raise MatrixError(f"{source}: duplicate class id {cls.id!r}")
        seen.add(cls.id)
        classes.append(cls)
    default = _build_class(data.get("default", {}), f"{source}: default", is_default=True)
    if default.id in seen:
        raise MatrixError(f"{source}: default id {default.id!r} duplicates a class id")
    markers = _str_list(data.get("gap_markers", []), f"{source}: gap_markers", allow_empty=True)
    gap_dir = data.get("gap_dir", "")
    if not isinstance(gap_dir, str):
        raise MatrixError(f"{source}: gap_dir must be a string, got {gap_dir!r}")
    return Matrix(tuple(classes), default, tuple(markers), gap_dir.strip(), source)


def load_matrix(path: "Path | str") -> Matrix:
    p = Path(path)
    if not p.is_file():
        raise MatrixError(f"matrix file not found: {p}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise MatrixError(f"{p}: invalid YAML: {exc}") from exc
    return parse_matrix(data, str(p))


# --------------------------------------------------------------------------- #
# Readers (seams)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class CommitInfo:
    sha: str
    parents: tuple[str, ...]
    message: str

    @property
    def subject(self) -> str:
        return self.message.strip().split("\n", 1)[0] if self.message.strip() else ""

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1


class GitReader(Protocol):
    def commits(self, base: str, head: str) -> list[CommitInfo]: ...
    def changed_files(self, sha: str) -> list[str]: ...


class SubprocessGitReader:
    """Real git, run in ``repo_root``."""

    def __init__(self, repo_root: "Path | str"):
        self.repo_root = Path(repo_root)

    def _git(self, *args: str) -> str:
        r = subprocess.run(["git", *args], cwd=str(self.repo_root), capture_output=True,
                           check=False)
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: "
                               f"{r.stderr.decode('utf-8', 'replace').strip()}")
        return r.stdout.decode("utf-8", "replace")

    def commits(self, base: str, head: str) -> list[CommitInfo]:
        out = self._git("log", "--reverse", "--topo-order",
                        "--format=%H%x1f%P%x1f%B%x1e", f"{base}..{head}")
        commits = []
        for chunk in out.split("\x1e"):
            chunk = chunk.strip("\n")
            if not chunk.strip():
                continue
            sha, parents, msg = chunk.split("\x1f", 2)
            commits.append(CommitInfo(sha.strip(), tuple(parents.split()), msg))
        return commits

    def changed_files(self, sha: str) -> list[str]:
        out = self._git("diff-tree", "--no-commit-id", "--name-only", "-r", "--no-renames",
                        "--root", "-z", sha)
        return sorted({p for p in out.split("\0") if p})


def read_records(records_dir: "Path | str") -> list[dict]:
    """Read every readable ``*.json`` object record in ``records_dir`` (sorted by name)."""
    d = Path(records_dir)
    if not d.is_dir():
        return []
    records = []
    for f in sorted(d.glob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict):
            rec.setdefault("run_id", f.stem)
            records.append(rec)
    return records


_cfg_repo_root: Path = _REPO_ROOT_DEFAULT
_cfg_git_reader: "GitReader | None" = None
_cfg_record_reader: Callable[[Path], list[dict]] = read_records
_cfg_gap_resolver: "Callable[[str], bool] | None" = None


def configure(*, repo_root: "Path | str | None" = None, git_reader: "GitReader | None" = None,
              record_reader: "Callable[[Path], list[dict]] | None" = None,
              gap_resolver: "Callable[[str], bool] | None" = None) -> None:
    """Override module defaults (tests). Calling with no args restores defaults."""
    global _cfg_repo_root, _cfg_git_reader, _cfg_record_reader, _cfg_gap_resolver
    _cfg_repo_root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    _cfg_git_reader = git_reader
    _cfg_record_reader = record_reader if record_reader is not None else read_records
    _cfg_gap_resolver = gap_resolver


def build_gap_resolver(gap_dir: "Path | str") -> Callable[[str], bool]:
    """Resolver for gap ids: an ``entries[].id`` row of ``index.yaml`` or a report file stem.

    The id must be a plain token (no path separators, no leading dot); the directory is
    listed once and ids are compared by equality, so an id can never escape ``gap_dir``.
    The index file's own stem never resolves.
    """
    d = Path(gap_dir)
    known: set[str] = set()
    if d.is_dir():
        for f in d.iterdir():
            if f.is_file() and f.stem != "index":
                known.add(f.stem)
        index = d / "index.yaml"
        if index.is_file():
            try:
                data = yaml.safe_load(index.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                data = {}
            rows = data.get("entries", []) if isinstance(data, dict) else []
            for row in rows if isinstance(rows, list) else []:
                if isinstance(row, dict) and isinstance(row.get("id"), str):
                    known.add(row["id"].strip())

    def resolve(gap_id: str) -> bool:
        return bool(_GAP_ID_RE.match(gap_id)) and gap_id in known

    return resolve


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #

def _sha_matches(record_sha: str, sha: str) -> bool:
    if not isinstance(record_sha, str):
        return False
    rs = record_sha.strip().lower()
    return len(rs) >= 8 and (sha.lower().startswith(rs) or rs.startswith(sha.lower()))


def _record_skills(rec: dict) -> set[str]:
    try:
        skills = _csr._compute_declared_from_record(rec)
    except (KeyError, TypeError, AttributeError):
        skills = set(rec.get("skills_invoked") or [])
    return {s.strip() for s in skills if isinstance(s, str) and s.strip()}


def _trailer_skills(message: str, matrix: Matrix) -> set[str] | None:
    entries = _csr._parse_declared_skills(message)
    if entries is None:
        return None
    tokens: set[str] = set()
    for e in entries:
        words = e.split()
        if words and matrix.marker_name(words[0]):
            tokens.add(words[0])  # marker names need not look like skill ids
            continue
        m = _TOKEN_RE.search(e)
        if m:
            tokens.add(m.group(0))
    return tokens


@dataclass
class CommitVerdict:
    sha: str
    subject: str
    verdict: str
    merge: bool = False
    classes: list[str] = field(default_factory=list)
    files_by_class: dict[str, list[str]] = field(default_factory=dict)
    declared_skills: list[str] = field(default_factory=list)
    declared_source: str = "none"
    run_ids: list[str] = field(default_factory=list)
    uncovered_classes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    unclassified_files: int = 0

    def to_dict(self) -> dict:
        return {
            "sha": self.sha, "subject": self.subject, "verdict": self.verdict,
            "merge": self.merge, "classes": self.classes,
            "files_by_class": self.files_by_class, "declared_skills": self.declared_skills,
            "declared_source": self.declared_source, "run_ids": self.run_ids,
            "uncovered_classes": self.uncovered_classes, "reasons": self.reasons,
            "notes": self.notes, "unclassified_files": self.unclassified_files,
        }


def _valid_gap_markers(declared: set[str], matrix: Matrix, resolver: Callable[[str], bool],
                       reasons: list[str]) -> list[str]:
    """Declared gap-marker tokens that resolve to a real gap id; reasons for the rest."""
    valid: list[str] = []
    for token in sorted(declared):
        name = matrix.marker_name(token)
        if name is None:
            continue
        gap_id = token[len(name) + 1:] if token != name else ""
        if not gap_id:
            reasons.append("gap marker without id")
        elif resolver(gap_id):
            valid.append(token)
        else:
            reasons.append(f"gap id not found: {gap_id}")
    return valid


def _audit_commit(c: CommitInfo, matrix: Matrix, git: GitReader, records: list[dict],
                  resolver: Callable[[str], bool]) -> CommitVerdict:
    v = CommitVerdict(sha=c.sha, subject=c.subject, verdict=VERDICT_PASS, merge=c.is_merge)
    if c.is_merge:
        v.notes.append("merge commit: content audited via constituent commits")
        return v
    by_class: dict[str, list[str]] = {}
    cls_by_id: dict[str, FileClass] = {}
    for path in git.changed_files(c.sha):
        cls = matrix.classify(path)
        by_class.setdefault(cls.id, []).append(path)
        cls_by_id[cls.id] = cls
    v.files_by_class = {k: sorted(by_class[k]) for k in sorted(by_class)}
    v.classes = sorted(by_class)
    needed = [cid for cid in v.classes if not cls_by_id[cid].exempt]
    if matrix.default.id in by_class:
        v.unclassified_files = len(by_class[matrix.default.id])
    for cid in v.classes:
        cls = cls_by_id[cid]
        if cls.exempt and cls.warn:
            v.notes.append(f"WARN: {len(by_class[cid])} file(s) in exempt class "
                           f"'{cid}' (no matrix rule)")
        if cls.token_required and not cls.exempt:
            v.notes.append(f"token required: class '{cid}' needs an override token reference")

    matched = [r for r in records if _sha_matches(r.get("commit_sha", ""), c.sha)
               and str(r.get("outcome", "success")).lower() not in _UNUSABLE_OUTCOMES]
    declared: set[str] = set()
    if matched:
        v.declared_source = "record"
        v.run_ids = sorted(str(r.get("run_id", "?")) for r in matched)
        for r in matched:
            declared |= _record_skills(r)
        if len(matched) > 1:
            v.notes.append(f"{len(matched)} records matched; skills unioned")
    else:
        trailer = _trailer_skills(c.message, matrix)
        if trailer is not None:
            v.declared_source = "trailer"
            declared = trailer
    v.declared_skills = sorted(declared)

    if not needed:
        v.notes.append("only exempt classes" if v.classes else "no file changes")
        return v
    if v.declared_source == "none":
        v.verdict = VERDICT_NO_RECORD
        v.uncovered_classes = needed
        return v
    reasons: list[str] = []
    valid_markers = _valid_gap_markers(declared, matrix, resolver, reasons)
    uncovered_skill: list[str] = []
    uncovered_gap: list[str] = []
    for cid in needed:
        cls = cls_by_id[cid]
        if declared & cls.skills:
            continue
        if (cls.allow_gap_markers or cls.no_skill) and valid_markers:
            v.notes.append(f"class '{cid}' covered by gap marker {valid_markers}")
            continue
        (uncovered_gap if cls.no_skill else uncovered_skill).append(cid)
    v.uncovered_classes = uncovered_skill + uncovered_gap
    if v.uncovered_classes:
        v.reasons = sorted(set(reasons))
        v.verdict = VERDICT_VIOLATION if uncovered_skill else VERDICT_GAP
    return v


def _never_resolves(_gap_id: str) -> bool:
    return False


def audit_range(base: str, head: str, matrix: Matrix, *, records_dir: "Path | str | None" = None,
                git: "GitReader | None" = None,
                record_reader: "Callable[[Path], list[dict]] | None" = None,
                gap_resolver: "Callable[[str], bool] | None" = None) -> dict:
    """Audit ``base..head``; returns a JSON-serialisable, deterministic report."""
    git = git or _cfg_git_reader or SubprocessGitReader(_cfg_repo_root)
    reader = record_reader or _cfg_record_reader
    resolver = gap_resolver or _cfg_gap_resolver
    if resolver is None:
        if matrix.gap_dir:
            resolver = build_gap_resolver(_cfg_repo_root / matrix.gap_dir)
        else:
            resolver = _never_resolves
    rdir = Path(records_dir) if records_dir is not None else _cfg_repo_root / DEFAULT_RECORDS_DIR
    records = reader(rdir)
    verdicts = [_audit_commit(c, matrix, git, records, resolver)
                for c in git.commits(base, head)]
    counts = {VERDICT_PASS: 0, VERDICT_VIOLATION: 0, VERDICT_NO_RECORD: 0, VERDICT_GAP: 0}
    for v in verdicts:
        counts[v.verdict] += 1
    return {
        "range": f"{base}..{head}",
        "matrix": matrix.source,
        "records_source": RECORDS_SOURCE_LOCAL if reader is read_records else RECORDS_SOURCE_INJECTED,
        "records_read": len(records),
        "caveats": list(CAVEATS),
        "commits": [v.to_dict() for v in verdicts],
        "summary": {"total": len(verdicts), **counts,
                    "unclassified_files": sum(v.unclassified_files for v in verdicts),
                    "unclassified_commits": sum(1 for v in verdicts if v.unclassified_files),
                    "clean": all(counts[k] == 0 for k in
                                 (VERDICT_VIOLATION, VERDICT_NO_RECORD, VERDICT_GAP))},
    }


def render_markdown(report: dict) -> str:
    def esc(s: str) -> str:
        return s.replace("|", "\\|").replace("\n", " ")

    lines = [f"# Skill provenance audit: `{report['range']}`", "",
             f"- records_source: {report['records_source']}",
             f"- records_read: {report['records_read']}"]
    lines += [f"- caveat: {cv}" for cv in report["caveats"]]
    lines += ["", "| sha | subject | classes | declared skills | verdict |",
             "|---|---|---|---|---|"]
    for c in report["commits"]:
        subj = c["subject"] if len(c["subject"]) <= 60 else c["subject"][:57] + "..."
        classes = ", ".join(c["classes"]) or ("(merge)" if c["merge"] else "(none)")
        skills = ", ".join(c["declared_skills"]) or "-"
        if c["declared_source"] != "none":
            skills += f" [{c['declared_source']}]"
        verdict = c["verdict"]
        if c["uncovered_classes"]:
            verdict += " (uncovered: " + ", ".join(c["uncovered_classes"]) + ")"
        if c["reasons"]:
            verdict += " [" + "; ".join(c["reasons"]) + "]"
        lines.append(f"| {c['sha'][:12]} | {esc(subj)} | {esc(classes)} | {esc(skills)} | {verdict} |")
    notes = [(c["sha"][:12], n) for c in report["commits"] for n in c["notes"]]
    if notes:
        lines += ["", "## Notes", ""] + [f"- {s}: {n}" for s, n in notes]
    s = report["summary"]
    lines += ["", "## Summary", "",
              f"- total: {s['total']}", f"- PASS: {s[VERDICT_PASS]}",
              f"- VIOLATION: {s[VERDICT_VIOLATION]}", f"- GAP: {s[VERDICT_GAP]}",
              f"- NO_RECORD: {s[VERDICT_NO_RECORD]}",
              f"- UNCLASSIFIED files: {s['unclassified_files']} "
              f"(in {s['unclassified_commits']} commits)",
              f"- clean: {str(s['clean']).lower()}", ""]
    return "\n".join(lines)


def _write(path: str, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Audit that every commit in a range is backed by a sanctioned skill "
                    "for each changed file class (skills-only enforcement, AC-5).")
    ap.add_argument("--base", required=True, help="exclusive base revision")
    ap.add_argument("--head", required=True, help="inclusive head revision")
    ap.add_argument("--matrix", default=str(DEFAULT_MATRIX), help="file-class matrix YAML")
    ap.add_argument("--records-dir", default=None,
                    help="skill-run records dir (default <repo>/reports/skill-runs)")
    ap.add_argument("--json-out", default=None, help="write JSON report here")
    ap.add_argument("--md-out", default=None, help="write Markdown report here")
    ap.add_argument("--fail-on-violation", action="store_true",
                    help="exit 1 when any commit is VIOLATION, GAP or NO_RECORD")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        matrix = load_matrix(args.matrix)
        report = audit_range(args.base, args.head, matrix, records_dir=args.records_dir)
    except (MatrixError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    md = render_markdown(report)
    print(md)
    if args.json_out:
        _write(args.json_out, json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.md_out:
        _write(args.md_out, md)
    if args.fail_on_violation and not report["summary"]["clean"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
