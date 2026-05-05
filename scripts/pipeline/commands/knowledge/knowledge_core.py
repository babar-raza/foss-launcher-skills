"""Knowledge model loading, content discovery, and evidence validation.

Extracted from audit.py. Provides the shared knowledge infrastructure used by
content audit, change guard, attach evidence, and evaluator tools.

Public API:
    Knowledge           — loaded knowledge model for a single family/platform
    KNOWLEDGE_ROOT      — Path("knowledge")
    PLATFORM_MAP        — {} (empty; content and knowledge paths now use the same names)
    PLATFORM_RMAP       — {} (empty; content and knowledge paths now use the same names)
    SITE_PATHS          — list of (site, path_pattern) tuples
    LOCALE_RE           — regex to detect translation file suffixes
    discover_content(family, platform) -> list[Path]
    discover_products() -> list[(family, platform)]
    infer_product(filepath) -> (family, platform) | (None, None)
    parse_frontmatter(filepath) -> dict
    verify_evidence(frontmatter, knowledge, filepath) -> list[Finding]
"""
from __future__ import annotations

import json
import re
import yaml
from pathlib import Path

# --- Standalone repo path resolution via config_loader ---
_HERE = Path(__file__).resolve().parent          # scripts/pipeline/commands/knowledge/
_PIPELINE = _HERE.parent.parent                  # scripts/pipeline/
_SCRIPTS = _HERE.parent.parent.parent            # scripts/
import sys as _sys
if str(_PIPELINE) not in _sys.path:
    _sys.path.insert(0, str(_PIPELINE))
if str(_SCRIPTS) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS))
from config_loader import (                       # noqa: E402
    resolve_knowledge_root as _resolve_knowledge_root,
    resolve_content_repo as _resolve_content_repo,
)
# --------------------------------------------------------

from commands.ops.token_ops import Finding  # noqa: E402 (moved to commands/ops/)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KNOWLEDGE_ROOT = _resolve_knowledge_root()

# Platform path mapping: content paths and knowledge directories now use the
# same name ("net" for .NET/C#). These dicts remain for API compatibility but
# are intentionally empty.
PLATFORM_MAP: dict[str, str] = {}
PLATFORM_RMAP: dict[str, str] = {}

# Site content paths relative to CONTENT_ROOT
SITE_PATHS = [
    ("products.aspose.org", "content/products.aspose.org/en/{family}/{platform}"),
    ("reference.aspose.org", "content/reference.aspose.org/en/{family}/{platform}"),
    ("docs.aspose.org", "content/docs.aspose.org/en/{family}/{platform}"),
    ("blog.aspose.org", "content/blog.aspose.org/{family}/{platform}"),
    ("kb.aspose.org", "content/kb.aspose.org/en/{family}/{platform}"),
]

# Locale codes to skip (translation files)
LOCALE_RE = re.compile(r"\.(?:ar|bg|ca|cs|da|de|el|es|et|fi|fr|he|hi|hr|hu|id|it|ja|ko|lt|lv|ms|nl|no|pl|pt|ro|ru|sk|sl|sr|sv|th|tr|uk|vi|zh)\.md$")


# ---------------------------------------------------------------------------
# Knowledge loader
# ---------------------------------------------------------------------------

class Knowledge:
    """Loaded knowledge model for a single family/platform."""

    def __init__(self, family, platform):
        self.family = family
        self.platform = platform
        merged = KNOWLEDGE_ROOT / family / platform / "merged"
        self.available = (merged / "api_surface.json").exists()
        if not self.available:
            return

        model = yaml.safe_load((merged / "model.yaml").read_text(encoding="utf-8"))
        self.version = model.get("version", "")
        self.repo_sha = model.get("repo_sha", "")

        api_list = json.loads((merged / "api_surface.json").read_text(encoding="utf-8"))

        # Build lookup structures
        self.classes = {}          # name -> class dict
        self.methods = {}          # name -> set of method names
        self.properties = {}       # name -> set of property names
        self.enum_members = {}     # name -> set of member names
        self.return_types = {}     # (class, method) -> return_type
        self.property_types = {}   # (class, property) -> type_string

        for cls in api_list:
            if not isinstance(cls, dict):
                continue
            name = cls.get("name", "")
            if not name:
                continue
            self.classes[name] = cls

            meths = self.methods.get(name, set())
            for m in cls.get("methods", []):
                if isinstance(m, dict):
                    mname = m.get("name", "")
                    meths.add(mname)
                    ret = m.get("return_type", "")
                    if ret:
                        self.return_types[(name, mname)] = ret.strip("'\"")
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
                        self.parents[cls_name] = info.get("bases", [])
                    elif isinstance(info, list):
                        self.parents[cls_name] = info
        # Also use bases from api_surface
        for cls in api_list:
            if isinstance(cls, dict) and cls.get("bases"):
                name = cls.get("name", "")
                if name and name not in self.parents:
                    self.parents[name] = cls["bases"]

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

        # Claims index (for evidence validation and api_to_claim mapping)
        claims_path = merged / "claims.json"
        self.claim_ids = set()
        self.api_to_claim = {}  # "ClassName.method" → claim_id (deterministic mapping)
        if claims_path.exists():
            claims_list = json.loads(claims_path.read_text(encoding="utf-8"))
            for c in claims_list:
                if not isinstance(c, dict):
                    continue
                cid = c.get("claim_id", "")
                if not cid:
                    continue
                self.claim_ids.add(cid)
                # Build reverse index: parse "ClassName.method(params) -> ret" from text field
                text = c.get("text", "")
                m = re.match(r"^(\w+)\.(\w+)\(", text)
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

    def has_method(self, cls_name, method_name):
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

    def has_property(self, cls_name, prop_name):
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

    def has_enum_member(self, enum_name, member_name):
        """Check if enum member exists."""
        return member_name in self.enum_members.get(enum_name, set())

    def get_return_type(self, cls_name, method_name):
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

    def get_property_type(self, cls_name, prop_name):
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

    def resolve_chain(self, placeholder):
        """Resolve a dotted placeholder like 'Scene.root_node' to a class name.

        Splits into (class, property), looks up the property type or method
        return type, and returns the resolved class name if it exists in
        self.classes. Returns None if unresolvable.
        """
        parts = placeholder.split(".")
        if len(parts) != 2:
            return None
        cls_name, member = parts
        if cls_name not in self.classes:
            return None
        # Try property type first
        resolved = self.get_property_type(cls_name, member)
        if not resolved:
            # Try method return type
            resolved = self.get_return_type(cls_name, member)
        if not resolved:
            return None
        # Normalize: strip List[], Optional[], etc.
        resolved = re.sub(r"^(?:List|Optional|Set|Tuple)\[(.+)\]$", r"\1", resolved)
        resolved = resolved.strip("'\"")
        if resolved in self.classes:
            return resolved
        return None

    def is_property_only(self, cls_name, member_name):
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

    def closest_match(self, candidates, target, limit=3):
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
# Content discovery
# ---------------------------------------------------------------------------

def discover_content(family: str, platform: str) -> list[Path]:
    """Find all English content .md files for a family/platform."""
    content_platform = PLATFORM_RMAP.get(platform, platform)
    files = []
    for site_name, pattern in SITE_PATHS:
        # Try mapped platform name first, fall back to original
        path = _resolve_content_repo() / "content" / Path(pattern.format(family=family, platform=content_platform)).relative_to("content")
        if not path.exists() and content_platform != platform:
            path = _resolve_content_repo() / "content" / Path(pattern.format(family=family, platform=platform)).relative_to("content")
        if path.exists():
            for f in sorted(path.rglob("*.md")):
                # Skip translation files
                if LOCALE_RE.search(f.name):
                    continue
                files.append(f)
    return files


def infer_product(filepath: Path) -> tuple[str, str] | tuple[None, None]:
    """Infer (family, platform) from a content file path."""
    parts = filepath.parts
    for i, p in enumerate(parts):
        if p in ("products.aspose.org", "reference.aspose.org",
                  "docs.aspose.org", "blog.aspose.org", "kb.aspose.org"):
            # Path structure: .../site/[en/]{family}/{platform}/...
            remaining = parts[i + 1:]
            if remaining and remaining[0] == "en":
                remaining = remaining[1:]
            if len(remaining) >= 2:
                family = remaining[0]
                platform = remaining[1]
                knowledge_platform = PLATFORM_MAP.get(platform, platform)
                return family, knowledge_platform
    return None, None


def discover_products() -> list[tuple[str, str]]:
    """Find all products with knowledge models (have api_surface.json)."""
    products = []
    for family_dir in sorted(KNOWLEDGE_ROOT.iterdir()):
        if not family_dir.is_dir() or family_dir.name.startswith("_"):
            continue
        for plat_dir in sorted(family_dir.iterdir()):
            if not plat_dir.is_dir():
                continue
            if (plat_dir / "merged" / "api_surface.json").exists():
                products.append((family_dir.name, plat_dir.name))
    return products


# ---------------------------------------------------------------------------
# Frontmatter evidence parser + validator (S-24)
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(filepath: Path) -> dict:
    """Extract YAML frontmatter dict from a markdown file. Returns {} if absent."""
    text = filepath.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def verify_evidence(frontmatter: dict, knowledge: Knowledge, filepath: Path) -> list[Finding]:
    """Validate the evidence: frontmatter block against the knowledge model.

    Returns a list of Finding objects.
    - Missing evidence block         → WARN
    - Stale model_sha                → WARN
    - Invalid claim_id               → FAIL  (only when claim index is populated)
    - Invalid api class/member       → FAIL
    """
    findings = []
    evidence = frontmatter.get("evidence")

    if not evidence or not isinstance(evidence, dict):
        findings.append(Finding(
            "WARN", filepath, 0,
            "Missing `evidence:` frontmatter block — run attach_evidence.py",
        ))
        return findings

    # Model SHA — detect staleness
    ev_sha = evidence.get("model_sha", "")
    if not ev_sha:
        findings.append(Finding(
            "WARN", filepath, 0,
            "`evidence.model_sha` is missing — pin the knowledge model SHA",
        ))
    elif ev_sha != knowledge.repo_sha:
        findings.append(Finding(
            "WARN", filepath, 0,
            f"Evidence stale: model updated to {knowledge.repo_sha[:8]}, "
            f"evidence references {ev_sha[:8]} — rerun attach_evidence.py",
        ))

    # Claim ID validation — only possible when claim index is populated.
    # An empty claim_ids set can mean either "no claims.json" or "empty claims.json";
    # in both cases we cannot distinguish valid from invalid IDs, so skip FAILs.
    can_validate_claims = bool(knowledge.claim_ids)
    if can_validate_claims:
        for claim_id in evidence.get("claims", []):
            if claim_id and claim_id not in knowledge.claim_ids:
                findings.append(Finding(
                    "FAIL", filepath, 0,
                    f"`evidence.claims` references unknown claim_id `{claim_id}`",
                    "Check merged/claims.json for valid IDs",
                ))
    elif evidence.get("claims"):
        findings.append(Finding(
            "WARN", filepath, 0,
            "Cannot validate claim IDs — claims.json is absent or empty for this product",
        ))

    # API reference validation
    for api_ref in evidence.get("apis", []):
        if not api_ref:
            continue
        if "." in api_ref:
            cls_name, member = api_ref.split(".", 1)
        else:
            cls_name, member = api_ref, None
        if cls_name not in knowledge.classes:
            findings.append(Finding(
                "FAIL", filepath, 0,
                f"`evidence.apis` references unknown class `{cls_name}` in `{api_ref}`",
                "Check merged/api_surface.json for valid class names",
            ))
        elif member and not knowledge.has_method(cls_name, member) \
                and not knowledge.has_property(cls_name, member) \
                and not knowledge.has_enum_member(cls_name, member):
            findings.append(Finding(
                "FAIL", filepath, 0,
                f"`evidence.apis` references unknown member `{api_ref}`",
                "Check merged/api_surface.json for valid methods/properties",
            ))

    return findings
