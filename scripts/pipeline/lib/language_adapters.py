"""
language_adapters.py -- per-language public-API delta adapters with an honest ground-truth tier.

CONTRACT: scripts/pipeline/lib/language_adapters.py
  purpose: Answering "did the public API change between two upstream commits, and how?" has two
           very different levels of certainty:
             GT-1  derived from a COMPILED artifact (e.g. `javap -public` over a built jar):
                   added/removed types, changed members incl. enum constants. Compiled-API truth.
             GT-2  derived from FILE-LEVEL evidence only (which source/changelog/readme/docs/test
                   files changed, and whether they sit on the language's API paths). It can say
                   "API files were touched"; it can NOT say what changed in the API.
           Every adapter reports its own `ground_truth_tier`, and adapter_for(platform) returns a
           GT-1 adapter only where one is really implemented, so a report can never silently
           pass GT-2 evidence off as GT-1 truth.
  contract: class LanguageAdapter:
              ground_truth_tier: str
              api_delta(old_ref, new_ref, *, repo_path, runner) -> dict
              build_artifact(ref, *, repo_path, runner, work_dir=None) -> dict
            Every external process (git, mvn, jar, javap) goes through the injected `runner`
            (`runner(cmd, *, cwd=None, timeout=None, env=None)` -> object with returncode /
            stdout / stderr), so tests are offline and need no JDK. JDK and Maven are discovered
            from the environment (JAVA_HOME / MAVEN_HOME, PATH, configurable search roots), never
            hard-coded.
  config:  config/language_api_paths.yaml -- per-language source extensions and API-path globs,
           keyed by the `platform` value of data/products.json. This module owns the loader and
           the file classifier (classify_paths) so the drift classifier and the GT-2 adapter can
           never disagree about what counts as "source" or "API".
  determinism: results are sorted; machine/time specific values (tool paths, work dirs) live
           under a `volatile` key.

Usage::

    from language_adapters import adapter_for, api_delta_with_fallback
    adapter = adapter_for("python")            # GT-2 generic
    adapter.ground_truth_tier                  # "GT-2"
    result = api_delta_with_fallback("java", old_sha, new_sha, repo_path=clone)
    result["ground_truth_tier"]                # "GT-1" if the JDK+Maven path ran, else "GT-2"
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

_LIB_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _LIB_DIR.parent

import yaml  # noqa: E402

DEFAULT_CONFIG_PATH = _PIPELINE_DIR / "config" / "language_api_paths.yaml"
_CONFIG_PATH = DEFAULT_CONFIG_PATH
_CONFIG_CACHE: "dict[tuple[str, int], dict[str, Any]]" = {}

GT1 = "GT-1"
GT2 = "GT-2"

Runner = Callable[..., Any]


class AdapterError(Exception):
    """An adapter step failed (git/build/javap error)."""


class AdapterUnavailable(AdapterError):
    """The adapter cannot run here (missing JDK/Maven ...). Callers fall back to GT-2."""


def configure(*, config_path: "Path | str | None" = None) -> None:
    """Point the module at another language_api_paths.yaml (tests); None restores the default."""
    global _CONFIG_PATH
    _CONFIG_PATH = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH


# ── process runner ───────────────────────────────────────────────────────────

def default_runner(cmd: "list[str]", *, cwd: "str | Path | None" = None,
                   timeout: "float | None" = 300, env: "dict[str, str] | None" = None):
    """subprocess.run wrapper that never raises for a missing tool / timeout: it returns a
    CompletedProcess with rc 127 / 124 and the reason in stderr, so callers classify instead of
    crashing a whole fleet run. Git never prompts (GIT_TERMINAL_PROMPT=0)."""
    full_env = dict(os.environ)
    full_env.setdefault("GIT_TERMINAL_PROMPT", "0")
    if env:
        full_env.update(env)
    try:
        return subprocess.run(
            cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", env=full_env,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", f"timeout after {timeout}s: {cmd[0]}")
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return subprocess.CompletedProcess(cmd, 127, "", f"cannot run {cmd[0]}: {exc}")


# ── config + file classification ─────────────────────────────────────────────

def load_language_config(path: "Path | str | None" = None) -> "dict[str, Any]":
    p = Path(path) if path is not None else _CONFIG_PATH
    key = (str(p), p.stat().st_mtime_ns)
    cached = _CONFIG_CACHE.get(key)
    if cached is None:
        cached = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        _CONFIG_CACHE.clear()
        _CONFIG_CACHE[key] = cached
    return cached


_REGEX_CACHE: "dict[tuple[str, bool], re.Pattern[str]]" = {}


def glob_to_regex(pattern: str, ignore_case: bool = False) -> "re.Pattern[str]":
    cached = _REGEX_CACHE.get((pattern, ignore_case))
    if cached is not None:
        return cached
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if pattern.startswith("**/", i):
                out.append("(?:.*/)?")
                i += 3
                continue
            if pattern.startswith("**", i):
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = pattern.find("]", i + 2)
            if j == -1:
                out.append(re.escape(c))
            else:
                body = pattern[i + 1:j]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    compiled = re.compile("^" + "".join(out) + "$", re.IGNORECASE if ignore_case else 0)
    _REGEX_CACHE[(pattern, ignore_case)] = compiled
    return compiled


def glob_match(pattern: str, path: str, *, ignore_case: bool = False) -> bool:
    """Case-SENSITIVE unless ignore_case (config: common.case_sensitive)."""
    return bool(glob_to_regex(pattern, ignore_case).match(path))


def _any(patterns: "list[str]", path: str, ignore_case: bool = False) -> bool:
    return any(glob_match(p, path, ignore_case=ignore_case) for p in patterns)


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def classify_paths(platform: str, files: "list[str]", *, config: "dict[str, Any] | None" = None) -> "dict[str, Any]":
    """Classify changed repo-relative paths for one platform.

    Returns {known_platform, unknown_reason, source_files, api_files, non_source_files} (sorted,
    de-duplicated). For a platform missing from the config, `known_platform` is False and
    source_files is only a count aid -- callers must not derive an API verdict from it.
    """
    cfg = config if config is not None else load_language_config()
    common = cfg.get("common") or {}
    ic = not bool(common.get("case_sensitive", True))
    langs = cfg.get("languages") or {}
    lang = langs.get(platform)
    paths = sorted({f.replace("\\", "/") for f in files if f})
    if lang is None:
        unk = cfg.get("unknown_platform") or {}
        exts = {e.lower() for e in unk.get("source_extensions") or []}
        non_src = common.get("non_source_path_patterns") or []
        src = [f for f in paths if _ext(f) in exts and not _any(non_src, f, ic)]
        return {
            "known_platform": False,
            "unknown_reason": unk.get("reason", "platform_not_in_language_api_paths"),
            "source_files": src,
            "api_files": [],
            "non_source_files": [f for f in paths if f not in set(src)],
        }
    exts = {e.lower() for e in lang.get("source_extensions") or []}
    non_src = list(common.get("non_source_path_patterns") or []) + list(lang.get("non_source_path_patterns") or [])
    api_inc = lang.get("api_path_patterns") or []
    api_exc = lang.get("api_exclude_patterns") or []
    source, api, other = [], [], []
    for f in paths:
        if _ext(f) in exts and not _any(non_src, f, ic):
            source.append(f)
            if _any(api_inc, f, ic) and not _any(api_exc, f, ic):
                api.append(f)
        else:
            other.append(f)
    return {"known_platform": True, "unknown_reason": None, "source_files": source,
            "api_files": api, "non_source_files": other}


def categorize_docs(files: "list[str]", *, config: "dict[str, Any] | None" = None) -> "dict[str, list[str]]":
    """CHANGELOG / README / docs / tests buckets (a file can sit in more than one). Matched
    case-insensitively: a file called changelog.md is a changelog."""
    common = (config if config is not None else load_language_config()).get("common") or {}
    paths = sorted({f.replace("\\", "/") for f in files if f})
    return {
        "changelog_files": [f for f in paths if _any(common.get("changelog_patterns") or [], f, True)],
        "readme_files": [f for f in paths if _any(common.get("readme_patterns") or [], f, True)],
        "docs_files": [f for f in paths if _any(common.get("docs_patterns") or [], f, True)],
        "test_files": [f for f in paths if _any(common.get("test_patterns") or [], f, True)],
    }


# ── adapter contract ─────────────────────────────────────────────────────────

class LanguageAdapter:
    """Contract. Subclasses MUST set a truthful ground_truth_tier."""

    platform: "str | None" = None
    ground_truth_tier: str = GT2

    def api_delta(self, old_ref: str, new_ref: str, *, repo_path: "str | Path", runner: Runner) -> "dict[str, Any]":
        raise NotImplementedError

    def build_artifact(self, ref: str, *, repo_path: "str | Path", runner: Runner,
                       work_dir: "str | Path | None" = None) -> "dict[str, Any]":
        raise NotImplementedError


_HEX_REF = re.compile(r"[0-9a-fA-F]{7,64}")
_REFS_NAME = re.compile(r"refs/[A-Za-z0-9._/+-]+")


def validate_ref(ref: str) -> str:
    """A revision passed to git must be a hex sha (7-64) or a full refs/... name. Anything else --
    notably a leading '-' (option injection), whitespace, '..' -- is refused before git runs."""
    if isinstance(ref, str) and (_HEX_REF.fullmatch(ref) or (
            _REFS_NAME.fullmatch(ref) and ".." not in ref and "/-" not in ref and not ref.endswith(("/", ".lock")))):
        return ref
    raise AdapterError(f"refusing unsafe or ambiguous git ref {ref!r} (need a hex sha or a refs/... name)")


def _git_changed(old_ref: str, new_ref: str, *, repo_path, runner) -> "list[tuple[str, str]]":
    validate_ref(old_ref)
    validate_ref(new_ref)
    res = runner(["git", "-C", str(repo_path), "diff", "--name-status", "--no-renames", "-z", old_ref, new_ref, "--"])
    if res.returncode != 0:
        raise AdapterError(f"git diff {old_ref}..{new_ref} failed: {(res.stderr or res.stdout or '').strip()[-200:]}")
    toks = [t for t in (res.stdout or "").split("\0")]
    if toks and toks[-1] == "":
        toks.pop()
    if len(toks) % 2:
        raise AdapterError("unparseable `git diff --name-status -z` output")
    return [(toks[i].strip()[:1], toks[i + 1]) for i in range(0, len(toks), 2)]


class GenericFileAdapter(LanguageAdapter):
    """GT-2: file-level derivation. Never claims compiled-API truth."""

    ground_truth_tier = GT2

    def __init__(self, platform: "str | None" = None, *, config: "dict[str, Any] | None" = None):
        self.platform = platform
        self._config = config

    def api_delta(self, old_ref, new_ref, *, repo_path, runner):
        cfg = self._config if self._config is not None else load_language_config()
        changes = _git_changed(old_ref, new_ref, repo_path=repo_path, runner=runner)
        files = [p for _s, p in changes]
        cls = classify_paths(self.platform or "", files, config=cfg)
        cats = categorize_docs(files, config=cfg)
        src = set(cls["source_files"])
        status = {p: s for s, p in changes}
        notes = ["GT-2 file-level derivation: names which files changed, not what changed in the compiled API"]
        if not cls["known_platform"]:
            notes.append(f"platform {self.platform!r} is not in language_api_paths.yaml: api_surface_touched is unknown")
        return {
            "ground_truth_tier": GT2,
            "method": "file-level",
            "compiled_api_truth": False,
            "platform": self.platform,
            "old_ref": old_ref,
            "new_ref": new_ref,
            "known_platform": cls["known_platform"],
            "changed_files": sorted(files),
            "added_source_files": sorted(p for p in src if status.get(p) == "A"),
            "removed_source_files": sorted(p for p in src if status.get(p) == "D"),
            "modified_source_files": sorted(p for p in src if status.get(p) not in ("A", "D")),
            "source_files": cls["source_files"],
            "api_path_files": cls["api_files"],
            "api_surface_touched": bool(cls["api_files"]) if cls["known_platform"] else None,
            **cats,
            "notes": notes,
        }

    def build_artifact(self, ref, *, repo_path, runner, work_dir=None):
        return {
            "ground_truth_tier": GT2, "built": False, "ref": ref,
            "reason": "no compiled-artifact adapter for this platform (generic GT-2 adapter)",
        }


# ── Java GT-1 ────────────────────────────────────────────────────────────────

_DEFAULT_JDK_ROOTS = (
    "C:/Program Files/Java", "C:/Program Files/Eclipse Adoptium", "C:/Program Files/Microsoft",
    "/usr/lib/jvm", "/Library/Java/JavaVirtualMachines", "/opt/java",
)
_DEFAULT_MAVEN_ROOTS = ("C:/Program Files/Apache/maven", "/opt/maven", "/usr/share/maven")

_TYPE_KEYWORD = re.compile(r"(?:^|\s)(?:class|interface|enum|@interface|record)\s+([\w.$]+)")
_SKIP_JAR_SUFFIXES = ("-sources", "-javadoc", "-tests", "-test-sources", "-shaded-sources")


def _exe_candidates(name: str) -> "list[str]":
    if name == "mvn":
        return ["mvn", "mvn.cmd", "mvn.bat"]
    return [name, name + ".exe"]


def _find_in_dir(directory: Path, name: str) -> "str | None":
    for cand in _exe_candidates(name):
        p = directory / cand
        if p.is_file():
            return str(p)
    return None


def find_tool(name: str, *, env: "dict[str, str]", which: "Callable[..., str | None] | None" = None,
              home_vars: "tuple[str, ...]" = (), search_roots: "list[str] | tuple[str, ...]" = ()) -> "str | None":
    """Locate an executable: <HOME_VAR>/bin, then PATH, then <root>/bin and <root>/*/bin (newest
    first). Returns None when not found."""
    which = which or shutil.which
    for var in home_vars:
        home = env.get(var)
        if home:
            hit = _find_in_dir(Path(home) / "bin", name)
            if hit:
                return hit
    for cand in _exe_candidates(name):
        hit = which(cand, path=env.get("PATH")) if which is shutil.which else which(cand)
        if hit:
            return hit
    for root in search_roots:
        r = Path(root)
        if not r.is_dir():
            continue
        hit = _find_in_dir(r / "bin", name)
        if hit:
            return hit
        for child in sorted((c for c in r.iterdir() if c.is_dir()), key=lambda c: c.name, reverse=True):
            hit = _find_in_dir(child / "bin", name) or _find_in_dir(child / "Contents" / "Home" / "bin", name)
            if hit:
                return hit
    return None


def _roots_from_env(env: "dict[str, str]", var: str, default: "tuple[str, ...]") -> "list[str]":
    raw = env.get(var)
    return [r for r in raw.split(os.pathsep) if r] if raw else list(default)


def parse_javap(text: str) -> "dict[str, dict[str, Any]]":
    """Parse `javap -public` output into {type: {decl, members:set, is_enum, constants:set}}.
    Non-public/non-protected types (package-private) are ignored."""
    out: dict[str, dict[str, Any]] = {}
    cur: "str | None" = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("Compiled from"):
            continue
        if not line.startswith(" ") and line.endswith("{"):
            m = _TYPE_KEYWORD.search(line)
            head = line.split(" extends ")[0].split(" implements ")[0]
            if m and re.search(r"\b(public|protected)\b", head):
                cur = m.group(1)
                out[cur] = {"decl": line.strip(), "members": set(),
                            "is_enum": " extends java.lang.Enum<" in line or bool(re.search(r"\benum\s", head)),
                            "constants": set()}
            else:
                cur = None
            continue
        if cur and line.startswith("  "):
            s = line.strip()
            if not s or s == "}":
                continue
            out[cur]["members"].add(s)
            if out[cur]["is_enum"]:
                cm = re.match(rf"^public static final {re.escape(cur)} (\w+);$", s)
                if cm:
                    out[cur]["constants"].add(cm.group(1))
    return out


def diff_javap(old: "dict[str, dict[str, Any]]", new: "dict[str, dict[str, Any]]") -> "dict[str, Any]":
    added = [{"type": t, "decl": new[t]["decl"], "members": len(new[t]["members"]),
              "member_list": sorted(new[t]["members"]), "is_enum": new[t]["is_enum"]}
             for t in sorted(set(new) - set(old))]
    removed = sorted(set(old) - set(new))
    changed: dict[str, Any] = {}
    for t in sorted(set(old) & set(new)):
        a = sorted(new[t]["members"] - old[t]["members"])
        r = sorted(old[t]["members"] - new[t]["members"])
        if a or r:
            changed[t] = {
                "added": a, "removed": r,
                "enum_constants_added": sorted(new[t]["constants"] - old[t]["constants"]),
                "enum_constants_removed": sorted(old[t]["constants"] - new[t]["constants"]),
            }
    return {"added_types": added, "removed_types": removed, "changed_types": changed}


class JavaGT1Adapter(LanguageAdapter):
    """GT-1: build both refs in temp copies, `javap -public` the jars, diff the public surface.

    `builder` (optional) replaces the Maven build: callable(checkout: Path, runner, tools: dict)
    -> Path of the jar to inspect. Used by tests with a tiny javac-based build.
    """

    platform = "java"
    ground_truth_tier = GT1

    def __init__(self, *, env: "dict[str, str] | None" = None, which: "Callable[..., str | None] | None" = None,
                 jdk_search_roots: "list[str] | None" = None, maven_search_roots: "list[str] | None" = None,
                 maven_args: "tuple[str, ...]" = ("-q", "-B", "-DskipTests", "package"),
                 builder: "Callable[..., Path] | None" = None, javap_chunk: int = 200,
                 build_timeout: float = 1800, keep_work: bool = False):
        self._env = dict(env) if env is not None else dict(os.environ)
        self._which = which
        self._jdk_roots = jdk_search_roots if jdk_search_roots is not None else _roots_from_env(
            self._env, "LANGUAGE_ADAPTER_JDK_ROOTS", _DEFAULT_JDK_ROOTS)
        self._mvn_roots = maven_search_roots if maven_search_roots is not None else _roots_from_env(
            self._env, "LANGUAGE_ADAPTER_MAVEN_ROOTS", _DEFAULT_MAVEN_ROOTS)
        self._maven_args = tuple(maven_args)
        self._builder = builder
        self._chunk = max(1, int(javap_chunk))
        self._build_timeout = build_timeout
        self._keep_work = keep_work

    # -- tool discovery
    def discover_tools(self, *, need_maven: bool = True) -> "dict[str, str]":
        tools: dict[str, str] = {}
        missing: list[str] = []
        for name in ("javap", "jar"):
            hit = find_tool(name, env=self._env, which=self._which, home_vars=("JAVA_HOME",),
                            search_roots=self._jdk_roots)
            if hit:
                tools[name] = hit
            else:
                missing.append(name)
        if need_maven:
            hit = find_tool("mvn", env=self._env, which=self._which, home_vars=("MAVEN_HOME", "M2_HOME"),
                            search_roots=self._mvn_roots)
            if hit:
                tools["mvn"] = hit
            else:
                missing.append("mvn")
        if missing:
            raise AdapterUnavailable(
                f"missing tool(s): {', '.join(missing)} (set JAVA_HOME/MAVEN_HOME, put them on PATH, "
                f"or set LANGUAGE_ADAPTER_JDK_ROOTS / LANGUAGE_ADAPTER_MAVEN_ROOTS)")
        return tools

    # -- build
    @staticmethod
    def _pick_jar(checkout: Path) -> Path:
        jars = [j for j in (checkout / "target").glob("*.jar")
                if not j.stem.endswith(_SKIP_JAR_SUFFIXES) and not j.name.startswith("original-")]
        if not jars:
            raise AdapterError(f"build produced no jar under {checkout / 'target'}")
        return sorted(jars, key=lambda j: (-j.stat().st_size, j.name))[0]

    def _checkout(self, ref: str, *, repo_path, runner, dest: Path) -> Path:
        validate_ref(ref)
        r = runner(["git", "clone", "--quiet", "--shared", "--no-checkout", str(repo_path), str(dest)])
        if r.returncode != 0:
            raise AdapterError(f"git clone failed: {(r.stderr or '').strip()[-200:]}")
        r = runner(["git", "-C", str(dest), "checkout", "--quiet", "--detach", ref])
        if r.returncode != 0:
            raise AdapterError(f"git checkout {ref} failed: {(r.stderr or '').strip()[-200:]}")
        return dest

    def _list_classes(self, jar: str, tools: "dict[str, str]", runner) -> "list[str]":
        r = runner([tools["jar"], "tf", jar])
        if r.returncode != 0:
            raise AdapterError(f"jar tf failed: {(r.stderr or '').strip()[-200:]}")
        names = []
        for n in (r.stdout or "").splitlines():
            n = n.strip()
            if not n.endswith(".class") or n.startswith("META-INF/"):
                continue
            base = n.rsplit("/", 1)[-1]
            if base in ("module-info.class", "package-info.class"):
                continue
            names.append(n[:-6].replace("/", "."))
        return sorted(set(names))

    def build_artifact(self, ref, *, repo_path, runner, work_dir=None, _tools=None):
        tools = _tools or self.discover_tools(need_maven=self._builder is None)
        own_tmp = work_dir is None
        work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="langadapter-"))
        dest = work / "checkout"
        try:
            self._checkout(ref, repo_path=repo_path, runner=runner, dest=dest)
            if self._builder is not None:
                jar = Path(self._builder(dest, runner, tools))
            else:
                r = runner([tools["mvn"], *self._maven_args], cwd=dest, timeout=self._build_timeout)
                if r.returncode != 0:
                    raise AdapterError(f"maven build failed at {ref}: {((r.stderr or '') + (r.stdout or '')).strip()[-300:]}")
                jar = self._pick_jar(dest)
            classes = self._list_classes(str(jar), tools, runner)
        except BaseException:
            if own_tmp and not self._keep_work:
                shutil.rmtree(work, ignore_errors=True)
            raise
        return {"ground_truth_tier": GT1, "built": True, "ref": ref, "classes": classes,
                "volatile": {"jar": str(jar), "work_dir": str(work)}}

    # -- javap
    def _dump(self, jar: str, classes: "list[str]", tools: "dict[str, str]", runner) -> "dict[str, dict[str, Any]]":
        merged: dict[str, dict[str, Any]] = {}
        for i in range(0, len(classes), self._chunk):
            chunk = classes[i:i + self._chunk]
            r = runner([tools["javap"], "-public", "-cp", jar, *chunk])
            if r.returncode != 0:
                raise AdapterError(f"javap failed: {(r.stderr or r.stdout or '').strip()[-300:]}")
            merged.update(parse_javap(r.stdout or ""))
        return merged

    def api_delta(self, old_ref, new_ref, *, repo_path, runner):
        tools = self.discover_tools(need_maven=self._builder is None)
        work = Path(tempfile.mkdtemp(prefix="langadapter-"))
        try:
            surfaces = []
            for label, ref in (("old", old_ref), ("new", new_ref)):
                art = self.build_artifact(ref, repo_path=repo_path, runner=runner,
                                          work_dir=work / label, _tools=tools)
                surfaces.append(self._dump(art["volatile"]["jar"], art["classes"], tools, runner))
        finally:
            if not self._keep_work:
                shutil.rmtree(work, ignore_errors=True)
        delta = diff_javap(*surfaces)
        return {
            "ground_truth_tier": GT1,
            "method": "javap-public-diff",
            "compiled_api_truth": True,
            "platform": "java",
            "old_ref": old_ref,
            "new_ref": new_ref,
            **delta,
            "summary": {
                "added_types": len(delta["added_types"]),
                "removed_types": len(delta["removed_types"]),
                "changed_types": len(delta["changed_types"]),
                "enum_constants_added": sum(len(v["enum_constants_added"]) for v in delta["changed_types"].values()),
            },
            "volatile": {"tools": dict(sorted(tools.items()))},
        }


# ── registry ─────────────────────────────────────────────────────────────────

_GT1_ADAPTERS: "dict[str, type[LanguageAdapter]]" = {"java": JavaGT1Adapter}


def adapter_for(platform: str, **kwargs: Any) -> LanguageAdapter:
    """GT-1 adapter where one is implemented, else the generic GT-2 adapter. The returned
    adapter's `ground_truth_tier` is always the truth about what it can deliver."""
    cls = _GT1_ADAPTERS.get(platform)
    if cls is not None:
        return cls(**kwargs)
    return GenericFileAdapter(platform, **{k: v for k, v in kwargs.items() if k == "config"})


def ground_truth_tier_for(platform: str) -> str:
    return GT1 if platform in _GT1_ADAPTERS else GT2


def api_delta_with_fallback(platform: str, old_ref: str, new_ref: str, *, repo_path: "str | Path",
                            runner: "Runner | None" = None, **adapter_kwargs: Any) -> "dict[str, Any]":
    """Run the platform's best adapter; if a GT-1 adapter is unavailable or fails, fall back to the
    GT-2 file-level result and SAY SO (`fallback_from`, `fallback_reason`) -- the returned
    `ground_truth_tier` is the tier actually achieved, never the one hoped for."""
    runner = runner or default_runner
    adapter = adapter_for(platform, **adapter_kwargs)
    try:
        return adapter.api_delta(old_ref, new_ref, repo_path=repo_path, runner=runner)
    except AdapterError as exc:
        if adapter.ground_truth_tier != GT1:
            raise
        result = GenericFileAdapter(platform).api_delta(old_ref, new_ref, repo_path=repo_path, runner=runner)
        result["fallback_from"] = GT1
        result["fallback_reason"] = f"{type(exc).__name__}: {exc}"
        return result
