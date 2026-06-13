"""Knowledge model loader.

Provides the Knowledge class.

Public API:
    Knowledge           — loaded knowledge model for a single family/platform

Removed symbols (see canonical homes):
    discover_content / discover_products / infer_product → content_discovery
    KNOWLEDGE_ROOT / PLATFORM_MAP / PLATFORM_RMAP        → content_discovery  (R-4)
    SITE_PATHS / LOCALE_RE                               → content_discovery  (R-4)
    verify_evidence                                       → evidence_verifier
    parse_frontmatter / _FRONTMATTER_RE                  → core.markdown

CLI Commands:
    diff {family} {platform} {repo_path}  — Compare repo SHA with stored SHA in model.yaml
"""
from __future__ import annotations

import hashlib
import json
import re
import yaml
from pathlib import Path


# ---------------------------------------------------------------------------
# R-4: constant re-exports removed; import from content_discovery directly.
# KNOWLEDGE_ROOT kept as a private import — used by Knowledge.__init__.
# ---------------------------------------------------------------------------

import sys  # noqa: E402
_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from content_discovery import KNOWLEDGE_ROOT as _KNOWLEDGE_ROOT  # noqa: E402  (internal only — R-4)

# _REPO_ROOT is still needed by Knowledge.__init__ path construction
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent  # scripts/pipeline/ -> scripts/ -> repo root


# ---------------------------------------------------------------------------
# Knowledge loader
# ---------------------------------------------------------------------------

class Knowledge:
    """Loaded knowledge model for a single family/platform.

    Construction is zero-I/O: no files are read until the first attribute
    access (``available``, ``classes``, ``methods``, etc.).  All data is loaded
    on first access via :meth:`_ensure_loaded`.
    """

    def __init__(self, family, platform, knowledge_root=None):
        self.family = family
        self.platform = platform
        _root = Path(knowledge_root) if knowledge_root is not None else _KNOWLEDGE_ROOT
        # Store path; no I/O here.
        self.__dict__["_merged"] = _root / family / platform / "merged"

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Load all knowledge artifacts from disk.  Idempotent (no-op after first call)."""
        if "_knowledge_loaded" in self.__dict__:
            return
        # Set sentinel FIRST to prevent recursion if called during load
        self.__dict__["_knowledge_loaded"] = True
        merged = self.__dict__["_merged"]

        available = (merged / "api_surface.json").exists()
        self.__dict__["available"] = available
        self.__dict__["workaround_members"] = {}

        if not available:
            # Set all data attributes to safe defaults so callers need not guard
            self.__dict__.update(dict(
                version="", repo_sha="", claims_hash="",
                enrichment_status=None, stale_since=None,
                classes={}, classes_by_import={},
                methods={}, properties={}, enum_members={},
                return_types={}, property_types={}, method_params={},
                parents={}, valid_imports=set(),
                claim_ids=set(), api_to_claim={},
                surface_tier=3, install_cmd="",
                snippet_index=[], _snippet_classes=set(), _snippet_methods=set(),
                class_importance={}, class_kind={},
            ))
            return

        model = yaml.safe_load((merged / "model.yaml").read_text(encoding="utf-8"))
        self.__dict__["version"] = model.get("version", "")
        self.__dict__["repo_sha"] = model.get("repo_sha", "")
        # enrichment_status: None means field absent (product bootstrapped before TC-4
        # tracking was added).  Callers treat None as "unknown — assume full" for
        # backward-compat.  "scout-only" means LLM enrichment was skipped or failed;
        # claim-based evaluators may produce false positives against scout-only knowledge.
        self.__dict__["enrichment_status"] = model.get("enrichment_status", None)
        self.__dict__["stale_since"] = model.get("stale_since", None)

        api_list = json.loads((merged / "api_surface.json").read_text(encoding="utf-8"))

        # Build lookup structures
        self.classes = {}          # name -> class dict
        self.classes_by_import = {}  # class_import -> class dict (FQ-name index)
        self.methods = {}          # name -> set of method names
        self.properties = {}       # name -> set of property names
        self.enum_members = {}     # name -> set of member names
        self.return_types = {}     # (class, method) -> return_type
        self.property_types = {}   # (class, property) -> type_string
        self.method_params = {}    # (class, method) -> set[int] of observed param counts (for overload detection)

        for cls in api_list:
            if not isinstance(cls, dict):
                continue
            name = cls.get("name", "")
            if not name:
                continue
            self.classes[name] = cls
            # FQ-name index: use class_import for disambiguation
            class_import = cls.get("class_import", "")
            if class_import:
                self.classes_by_import[class_import] = cls

            meths = self.methods.get(name, set())
            for m in cls.get("methods", []):
                if isinstance(m, dict):
                    mname = m.get("name", "")
                    meths.add(mname)
                    ret = m.get("return_type", "")
                    if ret:
                        self.return_types[(name, mname)] = ret.strip("'\"")
                    # Track param count for signature verification (overload detection)
                    params = m.get("params", [])
                    if isinstance(params, list):
                        key = (name, mname)
                        counts = self.method_params.get(key, set())
                        counts.add(len(params))
                        self.method_params[key] = counts
            self.methods[name] = meths

            props = self.properties.get(name, set())
            for p in cls.get("properties", []):
                if isinstance(p, dict):
                    pname = p.get("name", "")
                    props.add(pname)
                    ptype = p.get("type", "")
                    if ptype:
                        # Normalize: strip quotes and List[] wrapper
                        ptype = ptype.strip("'\"")
                        self.property_types[(name, pname)] = ptype
            self.properties[name] = props

            enums = self.enum_members.get(name, set())
            for e in cls.get("enum_members", []):
                if isinstance(e, dict):
                    enums.add(e.get("name", ""))
                elif isinstance(e, str):
                    enums.add(e)
            if enums:
                self.enum_members[name] = enums

        # Inheritance chain
        self.parents = {}  # class -> list of parent names
        graph_path = merged / "class_graph.json"
        if graph_path.exists():
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            if isinstance(graph, dict):
                for cls_name, info in graph.items():
                    if isinstance(info, dict):
                        # OBS-03: Filter self-referential bases defensively
                        self.parents[cls_name] = [b for b in info.get("bases", []) if b != cls_name]
                    elif isinstance(info, list):
                        self.parents[cls_name] = [b for b in info if b != cls_name]
            elif isinstance(graph, list):
                # Array format: [{"child": "Foo", "parent": "Bar", ...}, ...]
                for entry in graph:
                    if isinstance(entry, dict):
                        child = entry.get("child")
                        parent = entry.get("parent")
                        if child and parent and parent != child:  # OBS-03: filter self-ref
                            if child not in self.parents:
                                self.parents[child] = []
                            self.parents[child].append(parent)
        # Also use bases from api_surface
        for cls in api_list:
            if isinstance(cls, dict) and cls.get("bases"):
                name = cls.get("name", "")
                if name and name not in self.parents:
                    # OBS-03: Filter self-referential bases defensively
                    self.parents[name] = [b for b in cls["bases"] if b != name]

        # Derive valid import prefixes from file paths in api_surface
        self.valid_imports = set()
        for cls in api_list:
            if not isinstance(cls, dict):
                continue
            fp = cls.get("file", "")
            if not fp:
                continue
            # Convert file path to Python module: aspose/threed/Node.py -> aspose.threed
            parts = fp.replace("\\", "/").split("/")
            # Strip leading src/ if present
            if parts and parts[0] == "src":
                parts = parts[1:]
            # Build module prefix (all dirs before the .py file)
            if len(parts) >= 2:
                mod_parts = [p for p in parts[:-1] if not p.startswith("_")]
                if mod_parts:
                    self.valid_imports.add(".".join(mod_parts))
                    # Also add parent prefixes (e.g. aspose.threed -> aspose)
                    for i in range(1, len(mod_parts)):
                        self.valid_imports.add(".".join(mod_parts[:i]))

        # C#/.NET: supplement valid_imports with canonical_namespace values.
        # Directory-path-derived imports (above) do not capture C# namespaces
        # which are declared in source code, not reflected in directory structure.
        if self.platform in ("net", "dotnet"):
            for cls in api_list:
                if isinstance(cls, dict) and cls.get("canonical_namespace"):
                    self.valid_imports.add(cls["canonical_namespace"])

        # Claims index (for evidence validation and api_to_claim mapping)
        claims_path = merged / "claims.json"
        self.claim_ids = set()
        self.api_to_claim = {}  # "ClassName.method" (CLM-) or "ClassName" (ERC-) → claim_id
        self.claims_hash = ""   # sha256 of claims.json bytes (GAP-14 idempotency tracking)
        if claims_path.exists():
            claims_bytes = claims_path.read_bytes()
            self.claims_hash = hashlib.sha256(claims_bytes).hexdigest()
            claims_list = json.loads(claims_bytes.decode("utf-8"))
            # Sort by claim_id so the api_to_claim mapping is order-independent:
            # the lexicographically smallest claim_id always wins for each key.
            # CLM- sorts before ERC- so syntactic method-level keys are registered first.
            for c in sorted(claims_list, key=lambda c: c.get("claim_id") or ""):
                if not isinstance(c, dict):
                    continue
                cid = c.get("claim_id", "")
                if not cid:
                    continue
                self.claim_ids.add(cid)
                text = c.get("text", "")
                if cid.startswith("ERC-"):
                    # ERC- enriched claims: extract class names in two formats:
                    # 1. **ClassName** bold notation (Python/TypeScript ERC- claims)
                    # 2. Leading word validated against self.classes (Java ERC-
                    #    claims often start with the class name as plain text)
                    # Register class-only keys so the evidence mapper can resolve
                    # ERC- claims when a code token references a class but has no
                    # specific method (e.g. constructor calls, import references).
                    # These keys never conflict with CLM- ClassName.method keys.
                    found = re.findall(r'\*\*([A-Z]\w+)\*\*', text)
                    if not found:
                        # Try first word as a known class name.  This avoids
                        # false positives from English words ("The", "This").
                        first_word = text.split()[0] if text else ""
                        if first_word in self.classes:
                            found = [first_word]
                    for cls_name in found:
                        if cls_name not in self.api_to_claim:
                            self.api_to_claim[cls_name] = cid
                else:
                    # CLM- syntactic claims: two formats produced by scout.py:
                    # 1. Method:   "ClassName.method(params) -> ret"
                    # 2. Property: "ClassName.member property of type X"
                    # 3. Class:    "Class ClassName defined in src/..."  (no dot — skipped)
                    m = re.match(r"^(\w+)\.(\w+)\(", text)
                    if not m:
                        # Try property/field/event format (no parens)
                        m = re.match(r"^(\w+)\.(\w+)\s+(?:property|field|event)\b", text)
                    if m:
                        key = f"{m.group(1)}.{m.group(2)}"
                        # First claim wins (earlier in list = higher confidence)
                        if key not in self.api_to_claim:
                            self.api_to_claim[key] = cid

        # Surface tier
        idx_path = merged / "index.json"
        self.surface_tier = 3
        if idx_path.exists():
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
            cov = idx.get("api_coverage", {})
            self.surface_tier = cov.get("surface_tier", 3)

        # Install command
        install_path = merged / "install.md"
        self.install_cmd = ""
        if install_path.exists():
            for line in install_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("pip install") or line.startswith("npm install"):
                    self.install_cmd = line
                    break

        # Snippet index for snippet-source advisory checks
        self.snippet_index = []
        self._snippet_classes = set()   # all classes mentioned across snippets
        self._snippet_methods = set()   # all methods mentioned across snippets
        snippet_idx_path = merged / "snippets" / "snippets_index.json"
        if snippet_idx_path.exists():
            try:
                self.snippet_index = json.loads(
                    snippet_idx_path.read_text(encoding="utf-8"))
                for entry in self.snippet_index:
                    if not isinstance(entry, dict):
                        continue
                    for c in entry.get("classes_used", []):
                        self._snippet_classes.add(c)
                    for m in entry.get("methods_used", []):
                        self._snippet_methods.add(m)
            except (json.JSONDecodeError, OSError):
                pass

        # Coverage matrix — class importance scores and kind metadata
        # Used by CoverageEvaluator to avoid direct filesystem reads
        self.class_importance: dict[str, float] = {}
        self.class_kind: dict[str, str] = {}
        matrix_path = merged / "coverage_matrix.json"
        if matrix_path.exists():
            try:
                matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
                for entry in matrix:
                    if not isinstance(entry, dict):
                        continue
                    cname = entry.get("class", "")
                    if not cname:
                        continue
                    # Compute importance score same as CoverageEvaluator._compute_class_importance
                    mc = entry.get("method_count", 0)
                    pc = entry.get("property_count", 0)
                    base = min(1.0, (mc + pc) / 20)
                    if entry.get("has_tests"):
                        base += 0.15
                    if entry.get("has_doc"):
                        base += 0.1
                    if mc <= 1 and pc == 0:
                        base -= 0.2
                    self.class_importance[cname] = max(0.0, min(1.0, base))
                    self.class_kind[cname] = entry.get("kind", "")
            except (json.JSONDecodeError, OSError):
                pass

        # Workaround members — known private-API references that are correct
        workaround_path = merged / "workarounds.json"
        if workaround_path.exists():
            try:
                wk_list = json.loads(workaround_path.read_text(encoding="utf-8"))
                for entry in wk_list:
                    if isinstance(entry, dict):
                        cls = entry.get("class", "")
                        pm = entry.get("private_member", "")
                        if cls and pm:
                            self.workaround_members[(cls, pm)] = entry.get("reason", "")
            except (json.JSONDecodeError, OSError):
                pass

    def __getattr__(self, name: str):
        """Trigger lazy load on first access of any data attribute."""
        # Guard: private attrs that are missing → AttributeError immediately,
        # avoiding infinite recursion (e.g. _merged looked up before __init__ sets it).
        if name.startswith("_"):
            raise AttributeError(f"'Knowledge' object has no attribute {name!r}")
        self._ensure_loaded()
        try:
            return self.__dict__[name]
        except KeyError:
            raise AttributeError(f"'Knowledge' object has no attribute {name!r}")

    def has_method(self, cls_name: str, method_name: str) -> bool:
        """Check if method exists on class or any parent."""
        visited = set()
        to_check = [cls_name]
        while to_check:
            cn = to_check.pop()
            if cn in visited:
                continue
            visited.add(cn)
            if method_name in self.methods.get(cn, set()):
                return True
            # Python @property shows up as both method and property
            if method_name in self.properties.get(cn, set()):
                return True
            to_check.extend(self.parents.get(cn, []))
        return False

    def has_property(self, cls_name: str, prop_name: str) -> bool:
        """Check if property exists on class or any parent."""
        visited = set()
        to_check = [cls_name]
        while to_check:
            cn = to_check.pop()
            if cn in visited:
                continue
            visited.add(cn)
            if prop_name in self.properties.get(cn, set()):
                return True
            # Python @property appears as method with 0 params
            if prop_name in self.methods.get(cn, set()):
                return True
            to_check.extend(self.parents.get(cn, []))
        return False

    def has_enum_member(self, enum_name: str, member_name: str) -> bool:
        """Check if enum member exists."""
        return member_name in self.enum_members.get(enum_name, set())

    # --- Fully-qualified name lookups (S-1 disambiguation) ---

    def has_class_fq(self, class_import: str) -> bool:
        """Check if a class exists by its fully-qualified import path."""
        return class_import in self.classes_by_import

    def get_class_fq(self, class_import: str) -> dict | None:
        """Return the class dict for a fully-qualified import, or None."""
        return self.classes_by_import.get(class_import)

    def has_method_fq(self, class_import: str, method_name: str) -> bool:
        """Check if method exists on a class identified by FQ import path."""
        cls = self.classes_by_import.get(class_import)
        if cls is None:
            return False
        cls_name = cls.get("name", "")
        return self.has_method(cls_name, method_name)

    def has_property_fq(self, class_import: str, prop_name: str) -> bool:
        """Check if property exists on a class identified by FQ import path."""
        cls = self.classes_by_import.get(class_import)
        if cls is None:
            return False
        cls_name = cls.get("name", "")
        return self.has_property(cls_name, prop_name)

    def get_return_type(self, cls_name: str, method_name: str) -> str | None:
        """Get return type for class.method, walking inheritance."""
        visited = set()
        to_check = [cls_name]
        while to_check:
            cn = to_check.pop()
            if cn in visited:
                continue
            visited.add(cn)
            ret = self.return_types.get((cn, method_name))
            if ret:
                return ret
            to_check.extend(self.parents.get(cn, []))
        return None

    def get_property_type(self, cls_name: str, prop_name: str) -> str | None:
        """Get property type for class.property, walking inheritance."""
        visited = set()
        to_check = [cls_name]
        while to_check:
            cn = to_check.pop()
            if cn in visited:
                continue
            visited.add(cn)
            pt = self.property_types.get((cn, prop_name))
            if pt:
                return pt
            to_check.extend(self.parents.get(cn, []))
        return None

    def resolve_chain(self, placeholder: str) -> str | None:
        """Resolve a dotted placeholder like 'Workbook.getWorksheets.get' to a class name.

        Walks each hop via property type or method return type:
          Workbook -> getWorksheets() return type -> WorksheetCollection
          WorksheetCollection -> get() return type -> Worksheet
        Returns None at any hop that cannot be resolved from metadata.
        """
        parts = placeholder.split(".")
        if len(parts) < 2:
            return None
        cls_name = parts[0]
        if cls_name not in self.classes:
            return None
        for member in parts[1:]:
            resolved = self.get_property_type(cls_name, member)
            if not resolved:
                resolved = self.get_return_type(cls_name, member)
            if not resolved:
                return None
            resolved = re.sub(r"^(?:List|Optional|Set|Tuple)\[(.+)\]$", r"\1", resolved)
            resolved = resolved.strip("'\"")
            if resolved not in self.classes:
                return None
            cls_name = resolved
        return cls_name

    def is_property_only(self, cls_name: str, member_name: str) -> bool:
        """Check if member is a property but NOT a method on the class.

        Used to detect property-as-method anti-patterns (calling a property
        with parentheses). Walks the inheritance chain.
        """
        is_prop = False
        is_meth = False
        visited = set()
        to_check = [cls_name]
        while to_check:
            cn = to_check.pop()
            if cn in visited:
                continue
            visited.add(cn)
            if member_name in self.properties.get(cn, set()):
                is_prop = True
            if member_name in self.methods.get(cn, set()):
                is_meth = True
            to_check.extend(self.parents.get(cn, []))
        return is_prop and not is_meth

    def closest_match(self, candidates: list[str], target: str, limit: int = 3) -> list[str]:
        """Find closest matches by Levenshtein-like similarity."""
        if not candidates:
            return []
        scored = []
        tl = target.lower()
        for c in candidates:
            cl = c.lower()
            # Simple similarity: shared character ratio
            shared = sum(1 for a, b in zip(tl, cl) if a == b)
            score = shared / max(len(tl), len(cl)) if max(len(tl), len(cl)) > 0 else 0
            if score > 0.4:
                scored.append((score, c))
        scored.sort(reverse=True)
        return [c for _, c in scored[:limit]]


# ---------------------------------------------------------------------------
# Content discovery — R-1b: re-export stubs removed; import from content_discovery
# Evidence validator — R-3b: re-export stub removed; import from evidence_verifier
# parse_frontmatter — R-2b: removed; import from core.markdown
# _FRONTMATTER_RE   — R-2b: removed; import from core.markdown
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------


def diff(family: str, platform: str, repo_path: Path) -> str:
    """Compare repo SHA with stored SHA in model.yaml.
    
    Returns a diff report string.
    """
    import subprocess
    
    # Validate repo_path exists and is a directory
    if not repo_path.exists():
        return f"ERROR: Repo path does not exist: {repo_path}"
    if not repo_path.is_dir():
        return f"ERROR: Repo path is not a directory: {repo_path}"
    
    # Get current SHA from repo
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True
        )
        current_sha = result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"ERROR: Failed to get current SHA from repo: {e.stderr}"
    except FileNotFoundError:
        return f"ERROR: git command not found"
    
    # Get stored SHA from model.yaml
    knowledge = Knowledge(family, platform)
    if not knowledge.available:
        return f"ERROR: Knowledge model not available for {family}/{platform}"
    
    stored_sha = knowledge.repo_sha
    
    # Compare SHAs
    if current_sha == stored_sha:
        return f"SHA MATCH: Current repo SHA ({current_sha[:8]}) matches stored SHA in model.yaml"
    else:
        return (
            f"SHA MISMATCH:\n"
            f"  Current repo SHA: {current_sha[:8]}\n"
            f"  Stored SHA:       {stored_sha[:8]}\n"
            f"  Model version:    {knowledge.version}\n"
            f"\n"
            f"Run repo-scout to update the knowledge model."
        )


def main():
    """CLI entry point for knowledge_core commands."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python scripts/pipeline/lib/knowledge_core.py <command> [args...]")
        print("Commands:")
        print("  diff {family} {platform} {repo_path}  — Compare repo SHA with stored SHA")
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "diff":
        if len(sys.argv) != 5:
            print("Usage: python scripts/pipeline/lib/knowledge_core.py diff {family} {platform} {repo_path}")
            sys.exit(1)
        family = sys.argv[2]
        platform = sys.argv[3]
        repo_path = Path(sys.argv[4])
        result = diff(family, platform, repo_path)
        print(result)
    else:
        print(f"Unknown command: {command}")
        print("Available commands: diff")
        sys.exit(1)


if __name__ == "__main__":
    main()