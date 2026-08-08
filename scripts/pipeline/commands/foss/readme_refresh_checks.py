"""CONTRACT: deterministic checks for the /readme-refresh skill (plan:
C:\\Users\\prora\\.claude\\plans\\d-users-prora-onedrive-documents-github-humble-tome.md).

Full checks module for the /readme-refresh skill (S-ID assigned at registration; see
skills/readme-refresh.md), called from readme_refresh_run.py's ingest-candidate/recheck/push
subcommands. Two tiers throughout, consistent across every function below:
  - HARD GATE: a non-empty/True result blocks the state-machine transition. Used only where
    the check is genuinely unambiguous (a link target either exists on disk or doesn't; a
    command either matches upstream-issues.md's exact BLOCKING text or doesn't).
  - HEURISTIC / TWO-TIER: a non-empty result is a prompt for the mandatory human/agent
    judgment pass, never an automatic fail. Used wherever "is this actually a problem" is a
    content-quality judgment call a script can't fully automate (tone, member-list accuracy,
    diagram node duplication).

Diagram checks (Mermaid "## At a glance" flowchart, all real, implemented, hard-gate or
heuristic per function): check_diagram_connectivity() [hard gate], check_diagram_known_
subgraph_ids() [heuristic], check_diagram_matches_capability_dependencies() [hard gate once a
product has a data/diagram_capability_dependencies.json entry], check_diagram_suspicious_
direct_product_edge() [heuristic], check_diagram_capability_unreachable_from_product()
[heuristic], check_diagram_no_mechanism_duplicate_output() [heuristic], and check_only_
mermaid_block_changed() [hard gate for mermaid-only refresh runs].

Content checks (whole-README, all real, implemented): compute_link_caps(), count_aspose_
links(), check_enterprise_edition_naming() [heuristic], check_required_sections() [hard gate],
surgical_diff_check() [hard gate], check_license_link_target() [hard gate], check_process_
narration_smells() [heuristic], check_no_undisclosed_blocking_commands() [hard gate],
check_dropped_content() [hard gate at ingest-candidate -- a flagged item needs an explicit
disposition in dropped_claims.json before the transition can pass], check_no_excluded_domain_
links() [hard gate], check_named_member_accuracy() [heuristic -- see its own docstring for an
honest statement of what this heuristic implementation can and cannot verify, versus the
full per-language compiler-grade extraction the plan's Verification pass section describes],
check_api_reference_intro_names_classes() [heuristic].

check_diagram_matches_capability_dependencies (spec'd 2026-08-06, plan section
"Capability-dependency edges") is a hard gate once a product has a recorded
pipeline_edges list (data/diagram_capability_dependencies.json) -- a no-op,
always-pass when pipeline_edges is None (nothing recorded to contradict).
Compares the drawn diagram's edges against the recorded [from, to] pairs:
every recorded pair must have a real from---to edge, `to` must not also carry
a direct PRODUCT---to edge (the barcode/python C5/C6 contradiction this exists
to catch), and any drawn Capability-to-Capability edge absent from the record
is flagged as undeclared (either a real find not yet recorded, or drift).

check_diagram_suspicious_direct_product_edge and
check_diagram_capability_unreachable_from_product (both spec'd 2026-08-06) are
heuristic, non-blocking tripwires. The former flags a Capabilities node wired
both directly from PRODUCT and from a sibling Capability -- the contradictory
double-path shape found live in barcode/python's 2026-08-05 fix (honest recall:
catches only defects with *some* existing Capability-to-Capability edge to
contradict, not the far more common "edge simply never drawn" shape). The
latter flags a Capabilities node with zero inbound edges from PRODUCT or a
sibling Capability -- a regression tripwire for future edits, harmless no-op
against pre-fix diagrams.

check_only_mermaid_block_changed (spec'd 2026-08-06, "Hardened design" section
-- the mermaid-only-refresh enforcement mechanism) extracts the full fenced
```mermaid ... ``` block (fences included) from both an old and new copy of a
README, replaces it with a fixed placeholder in each, and asserts the
remainder is byte-identical. This is the mechanical gate for "a diagram
refresh must touch only the diagram" -- it exists specifically because no
such mechanism existed anywhere in this repo before, and this session already
observed 5 of 8 parallel agents pick up a contaminated pre-edit snapshot once
(a different, complementary risk this check does not itself prevent -- it
only catches a bad *result*, not a bad starting snapshot).

check_diagram_known_subgraph_ids (spec'd 2026-08-06, plan section "Archetype-aware
structure and content rules") is a non-blocking tripwire: flags any `## At a glance`
subgraph ID outside the canonical set {Inputs, FromScratch, Capabilities, Outputs}
-- either a typo'd canonical ID or a genuinely new archetype shape not yet added to
the canonical set. check_diagram_connectivity's ID-based classifier (below) is a
strict allow-list, so an unrecognized ID would otherwise silently drop out of
connectivity checking rather than erroring; this check exists specifically to
surface that silent-drop case for human/agent judgment, never an automatic fail.

check_diagram_no_mechanism_duplicate_output (spec'd 2026-08-05, plan section
"Never split one output artifact into multiple Output nodes purely by
delivery mechanism") is a heuristic pre-filter, two-tier like the other
2026-08-05 checks: it flags any pair of `## At a glance` Output nodes whose
labels share a significant word and where at least one label contains a
delivery-mechanism keyword (path/stream/buffer/bytes/in-memory/file) while
their inbound Capability-edge sets differ. Found live via direct user review
of cells/cpp's rendered GitHub diagram: `.xlsx workbook (path)` and `.xlsx
workbook (binary stream)` were split into two Output nodes, but the stream
variant was wired from only 1 of 5 Capability nodes, falsely implying only
that one capability's work could be stream-saved -- when in reality path vs.
stream is an orthogonal Save() I/O mechanism, unrelated to which capability
populated the workbook. cells/rust had the same defect, worse (3 delivery
variants, 2 gated to a single capability). A portfolio-wide mechanical
pre-filter + manual review confirmed these were the only 2 of 30 files with
this exact defect -- several near-misses (3d/net, cells/python, email/cpp,
email/net, email/python) were checked and confirmed to be genuinely
different output *content*, not mechanism duplicates, and correctly left
alone. A hit is a prompt for the mandatory judgment pass ("same artifact,
different mechanism" vs. "genuinely different content"), never an automatic
fail.

check_api_reference_intro_names_classes (spec'd 2026-08-05, plan section "API
reference intro sentence must name real hub classes") is a cheap regex
tripwire, two-tier like check_process_narration_smells: it flags the
"## API reference" intro sentence (the text between the H2 heading and its
`<details>` fold) when it matches either confirmed bad form -- a bare
"ships N public types. Selected entry points:" filler, or a bare
`namespace.*`/`package.*` wildcard with no backtick-quoted class name in the
same sentence -- as a prompt for the mandatory judgment pass to rewrite it
naming the product's real hub class(es), never an automatic fail (naming a
real hub class is a content-quality judgment call, not mechanically
decidable). Found live on direct user review of 3d/net's rendered GitHub PR
page: the section read as nearly empty (one generic sentence, then everything
real hidden behind a single `<details>` fold with zero class names visible).
A read-only 30-file survey run in response confirmed this is inconsistent
portfolio-wide, not a 3d/net-specific defect -- 9 of 30 files have the weak
pattern (3d/net, pdf/net, cells/net, 3d/java, cells/java, slides/java,
email/net, note/python, 3d/python) while the other 21 already name real hub
classes correctly (e.g. cells/cpp: "The primary entry point is `Workbook`,
which owns a `WorksheetCollection` of `Worksheet` objects.").

check_named_member_accuracy (spec'd 2026-08-05, plan section "Named-member API
claims must be individually verified against real source") is the newest spec'd
check -- it targets a defect class check_dropped_content cannot see: a README
bullet of the form "`ClassName` -- `member1`, `member2`, ..." can name a real,
present class while still listing a wrong member set (a member that doesn't
exist on the real class, or a combined Load/Save-style bullet that's silently
just one side's property list). This was found live in 3d/python's "Format
load/save options" API reference subsection -- ObjSaveOptions had 5 real
Save-only properties silently missing from a combined bullet, and a glTF bullet
claimed an `export_textures` property that exists on neither real class.
check_dropped_content only tests presence (does old topic X still appear
somewhere); this checks accuracy (is the specific technical claim about a
present topic actually true of the real source) -- a different failure mode
needing a different check, not wider coverage of the same one.

check_diagram_connectivity parses the ```mermaid flowchart``` block in a README,
classifies each `subgraph` by its ID (Inputs / FromScratch / Capabilities / Outputs
-- changed 2026-08-06 from classifying by label text, see below), and verifies
every node declared inside the Capabilities subgraph has a path (via the diagram's
edges) to at least one node in the Outputs subgraph. A capability node with no such
path is an "orphan" -- the diagram visually claims the capability exists but never
shows it producing anything.

This check is purely structural. It cannot tell whether a node's claim is true
(fabricated node) or stale (correct at generation time, false after a later
correction) -- those require comparing against the README's own Key Capabilities /
Scope and limitations sections and the paired upstream-issues.md, which stays
agent judgment, not a script.

ID-based classification (2026-08-06): originally this classified by matching
substrings ("input"/"capabilit"/"output") in the subgraph's display LABEL text.
That stopped being a safe signal once the plan's archetype system (Template
section, "Archetype-aware structure and content rules") started allowing display
labels to vary per product archetype -- e.g. a generative product's Inputs
subgraph is titled "Input data and options", not "Inputs and formats". The
subgraph ID (`subgraph Inputs[...]` -- the bare word before the `[`) stays a
stable, non-prose anchor regardless of what the label says, so classification now
keys off group(1) (the ID) instead of group(2) (the label). Verified backward
compatible against the full 30-file corpus before this landed: every existing
diagram already writes an ID that equals its own label text verbatim, so this is
a no-op for all pre-existing files. `Inputs` and `FromScratch` (the new subgraph
a hybrid-archetype product's diagram may add, per the Template section) are both
classified into a single "source" bucket -- the connectivity check's BFS logic
never enumerated Inputs subgraphs in the first place (it only walks forward from
Capabilities to Outputs), so folding FromScratch into the same bucket needed no
change to that logic, only to classification.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field

_MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
_MERMAID_BLOCK_FULL_RE = re.compile(r"```mermaid\s*\n.*?```", re.DOTALL)
_MERMAID_BLOCK_PLACEHOLDER = "```mermaid\n<MERMAID_BLOCK_CHECKED_SEPARATELY>\n```"
_SUBGRAPH_START_RE = re.compile(r'^\s*subgraph\s+([A-Za-z0-9_]+)(?:\["(.*?)"\])?\s*$')
_SUBGRAPH_END_RE = re.compile(r"^\s*end\s*$")
_NODE_DECL_RE = re.compile(r'^\s*([A-Za-z0-9_]+)\s*\["(.*?)"\]\s*$')
_CHAIN_ARROW_SPLIT_RE = re.compile(r"-{1,3}>?")
_CHAIN_NODE_TOKEN_RE = re.compile(r'^\s*([A-Za-z0-9_]+)\s*(?:\["(.*?)"\])?\s*$')

# Eleventh incident / MT025 (2026-08-08): Starting Points / Outputs format-purity check
# constants. See check_diagram_container_format_purity's docstring for the full design
# rationale -- this is a *seed* list harvested from 10 of 30 real products during the
# forensic investigation, deliberately not claimed complete (plan section "Tradeoffs, risks,
# and honest limits").
_CONTAINER_CONNECTOR_ALLOWLIST = frozenset({
    "a", "an", "the", "and", "or", "existing",
    "document", "documents", "file", "files",
    "workbook", "workbooks", "package", "packages",
    "container", "containers", "string", "strings",
    "byte", "bytes", "text", "plain",
    "image", "images", "raster",
    "presentation", "presentations",
    "stream", "path", "single", "multi", "page", "pages",
    "serialized", "serialised", "flat", "storage", "storages",
})
# Eleventh incident / MT025 sanity pass (2026-08-08): running the purity check against all 30
# real candidates found `data/format_descriptions.json` (56 entries, a full multi-language site
# content registry, not owned by this plan) is genuinely missing several formats this exact
# portfolio legitimately produces/consumes -- confirmed by direct lookup, not assumed. Adding
# real, full-content entries to that registry (16 locales/format) is out of this plan's scope;
# this is a small, diagram-purity-scoped supplement, names only, sourced directly from this
# sanity pass's own confirmed findings (never guessed). Expect real additions here as Phase 1/2
# execution reaches products outside the 10 sampled during the original investigation.
_DIAGRAM_SUPPLEMENTARY_FORMAT_NAMES = frozenset({
    "PPTX", "OOXML", "CFB", "MSG", "EML", "STL", "OBJ", "GLTF", "GLB", "FBX", "COLLADA", "3MF",
    "CSV", "JSON", "OPC", "MARKDOWN", "DVI", "WOFF", "WOFF2", "APNG", "PLY", "U3D", "RVM", "JT",
    "A3DW", "AMF", "DRACO", "USD",
})
_HYBRID_FROM_SCRATCH_LITERAL = "Nothing — authored from scratch"
# Tolerant of the ASCII "--" a composing agent (or a test fixture) may write in place of the
# real em dash "--" used in production content -- both are real, observed forms, not just a
# test-vs-prod inconsistency to paper over.
_HYBRID_FROM_SCRATCH_RE = re.compile(r"^Nothing\s*(?:--|—)\s*authored from scratch$")
_PURITY_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*")
_VERSION_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)*$")
_ARCHETYPES_REQUIRING_STARTING_POINTS = frozenset({"transform", "compile"})


def _parse_edge_chain(line: str) -> list[tuple[str, str | None]] | None:
    """Parse a possibly-chained edge line -- 'A --> B', 'A --- B', or an N-hop chain like
    'StartingPoints --> PRODUCT --> Capabilities --> Outputs' (the 2026-08-08 simplified
    diagram's own fixed container-chain shape) -- into an ordered list of (node_id, label)
    tuples. Returns None if the line doesn't look like an edge chain at all (every
    arrow-delimited segment must resolve to a single node token, optionally labeled).

    A single-regex, whole-line-anchored approach (the pre-2026-08-08 `_EDGE_RE`) only ever
    matched a single A-->B hop -- a real bug found via this module's own smoke-test against
    a real mockup file: a 3-hop chain line silently matched nothing at all, so
    check_diagram_shape saw zero edges and reported every chain edge as "missing" even
    against a correctly-formed diagram.
    """
    segments = _CHAIN_ARROW_SPLIT_RE.split(line)
    if len(segments) < 2:
        return None
    nodes: list[tuple[str, str | None]] = []
    for segment in segments:
        match = _CHAIN_NODE_TOKEN_RE.match(segment)
        if not match:
            return None
        nodes.append((match.group(1), match.group(2)))
    return nodes


@dataclass
class DiagramGraph:
    node_subgraph: dict = field(default_factory=dict)  # node_id -> top-level container kind
    node_label: dict = field(default_factory=dict)  # node_id -> label text
    edges: list = field(default_factory=list)  # list of (a, b)
    subgraph_kinds_seen: set = field(default_factory=set)
    top_level_subgraph_order: list = field(default_factory=list)  # e.g. ["starting_points", "capabilities", "outputs"]
    capability_columns: list = field(default_factory=list)  # list of [node_id, ...] in document order


# 2026-08-08 diagram simplification (Tenth incident): the diagram shrinks to exactly
# Product -> Core Capabilities -> Outputs, with an optional 2-line Starting Points
# container ahead of Product for hybrid-archetype products only. `Inputs`/`FromScratch`
# (the pre-2026-08-08 archetype-system subgraph IDs) are retired -- a diagram still using
# them fails check_diagram_shape below and needs re-rendering under MT024, not a silent
# migration shim.
_CANONICAL_SUBGRAPH_IDS = {"StartingPoints", "Capabilities", "Outputs"}


def _classify_subgraph(subgraph_id: str) -> str | None:
    if not subgraph_id:
        return None
    if subgraph_id == "Capabilities":
        return "capabilities"
    if subgraph_id == "Outputs":
        return "outputs"
    if subgraph_id == "StartingPoints":
        return "starting_points"
    return None


def extract_mermaid_block(markdown_text: str) -> str | None:
    match = _MERMAID_BLOCK_RE.search(markdown_text)
    if not match:
        return None
    return match.group(1)


def parse_diagram(mermaid_text: str) -> DiagramGraph:
    """Parse a `## At a glance` Mermaid flowchart into a DiagramGraph.

    Nesting-aware (2026-08-08): the 2-column capability layout uses a nested subgraph
    inside `Capabilities` per column (e.g. `subgraph capl[" "]` / `subgraph capr[" "]`).
    A stack tracks the currently-open container so a nested, non-canonical subgraph ID
    directly inside `Capabilities` is treated as a column boundary (not an unknown top-
    level container) -- its nodes still classify as "capabilities" and get appended to
    `capability_columns` as their own column list. A product with 5 or fewer
    capabilities has no nested column subgraph at all; its nodes are declared directly
    inside `Capabilities` and all land in `capability_columns[0]` (a single, implicit
    column) in declaration order.
    """
    graph = DiagramGraph()
    stack: list[str] = []  # "starting_points" | "capabilities" | "outputs" | "_column" | "_unknown"

    for raw_line in mermaid_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("flowchart") or line.startswith("direction"):
            continue

        start_match = _SUBGRAPH_START_RE.match(line)
        if start_match:
            sid = start_match.group(1)
            kind = _classify_subgraph(sid)
            if kind is not None:
                graph.subgraph_kinds_seen.add(kind)
                graph.top_level_subgraph_order.append(kind)
                stack.append(kind)
            elif stack and stack[-1] == "capabilities":
                graph.capability_columns.append([])
                stack.append("_column")
            else:
                stack.append("_unknown")
            continue

        if _SUBGRAPH_END_RE.match(line):
            if stack:
                stack.pop()
            continue

        node_match = _NODE_DECL_RE.match(line)
        if node_match:
            node_id, label = node_match.group(1), node_match.group(2)
            graph.node_label[node_id] = label
            if stack:
                top = stack[-1]
                effective_kind = "capabilities" if top == "_column" else top
                if effective_kind in ("starting_points", "capabilities", "outputs"):
                    graph.node_subgraph[node_id] = effective_kind
                if effective_kind == "capabilities":
                    if top == "_column":
                        graph.capability_columns[-1].append(node_id)
                    else:
                        if not graph.capability_columns:
                            graph.capability_columns.append([])
                        graph.capability_columns[0].append(node_id)
            continue

        chain = _parse_edge_chain(line)
        if chain:
            for node_id, label in chain:
                if label:
                    graph.node_label.setdefault(node_id, label)
            for (from_id, _), (to_id, _) in zip(chain, chain[1:]):
                graph.edges.append((from_id, to_id))
            continue
        # Anything else (comments, styling directives) is ignored -- not our concern.

    return graph


def check_diagram_shape(markdown_text: str) -> list[dict]:
    """Hard gate (2026-08-08 diagram simplification, replaces the pre-simplification
    check_diagram_connectivity orphan-reachability check, which no longer applies once
    there are no per-node edges to be unreachable through).

    The At-a-glance diagram must be exactly `Product -> Core Capabilities -> Outputs`,
    with an optional `Starting Points -> Product` prefix (hybrid archetype only, exactly
    one Starting Points container, never more). No individual capability-to-output edges,
    no duplicate containers, no missing containers. Returns a list of {"reason": ...}
    findings, empty if the diagram matches this shape exactly.
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return [{"reason": "no mermaid block found"}]

    graph = parse_diagram(mermaid_text)
    findings: list[dict] = []

    kinds = graph.top_level_subgraph_order
    starting_count = kinds.count("starting_points")
    cap_count = kinds.count("capabilities")
    out_count = kinds.count("outputs")

    if cap_count != 1:
        findings.append({"reason": f"expected exactly 1 Capabilities container, found {cap_count}"})
    if out_count != 1:
        findings.append({"reason": f"expected exactly 1 Outputs container, found {out_count}"})
    if starting_count > 1:
        findings.append({"reason": f"expected at most 1 Starting Points container, found {starting_count}"})

    has_product = bool(re.search(r'^\s*PRODUCT\s*\["', mermaid_text, re.MULTILINE))
    if not has_product:
        findings.append({"reason": "no PRODUCT node found"})

    if cap_count == 1 and out_count == 1 and has_product:
        expected_chain = (["StartingPoints"] if starting_count == 1 else []) + [
            "PRODUCT", "Capabilities", "Outputs"
        ]
        chain_edges = set(graph.edges)
        for a, b in zip(expected_chain, expected_chain[1:]):
            if (a, b) not in chain_edges:
                findings.append({"reason": f"missing chain edge {a} --> {b}"})

        allowed_edges = set(zip(expected_chain, expected_chain[1:]))
        extra_edges = [e for e in graph.edges if e not in allowed_edges]
        if extra_edges:
            findings.append({
                "reason": f"edge(s) outside the fixed container chain (individual node "
                          f"wiring is retired under the 2026-08-08 simplification): {extra_edges}"
            })

    return findings


def check_diagram_starting_points_presence(markdown_text: str, archetype: str) -> list[dict]:
    """Hard gate (2026-08-08, Eleventh incident / MT025). Enforces the archetype -> Starting
    Points presence rule that check_diagram_hybrid_reverification's old universal "only hybrid"
    clause used to (wrongly) also enforce as a side effect:

      - generative: the container must be ABSENT (barcode/python has no format-based input at
        all -- unchanged from the original design, now actively gated instead of true only by
        omission).
      - transform / compile: the container must be PRESENT with >= 1 node -- the actual
        Eleventh-incident defect this check exists to close. Direct investigation confirmed 9 of
        9 sampled non-hybrid, non-generative products had silently lost this container entirely.
      - hybrid: the container must be PRESENT with exactly 2 nodes (the existing, unchanged,
        already-approved "An existing X document" / "Nothing -- authored from scratch" shape).

    This check answers "is a Starting Points container appropriate at all, and how big" --
    check_diagram_hybrid_reverification (below) answers a narrower, hybrid-only question ("is
    THIS hybrid classification fresh"). The two used to be conflated in one function; splitting
    them is what makes it possible for a transform-archetype product to have a Starting Points
    container at all (previously hard-blocked, see that function's docstring).

    Returns a list of {"reason": ...} findings, empty if presence/count matches the archetype's
    rule.
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return [{"reason": "no mermaid block found"}]
    graph = parse_diagram(mermaid_text)
    present = "starting_points" in graph.subgraph_kinds_seen
    node_count = sum(1 for kind in graph.node_subgraph.values() if kind == "starting_points")

    if archetype == "generative":
        if present:
            return [{
                "reason": "generative archetype must have NO Starting Points container (no "
                          f"format-based input exists) -- found one with {node_count} node(s)",
            }]
        return []

    if archetype in _ARCHETYPES_REQUIRING_STARTING_POINTS:
        if not present or node_count == 0:
            return [{
                "reason": f"'{archetype}' archetype requires a Starting Points container "
                          "listing the product's real, distinct input formats -- none found "
                          "(this is the Eleventh-incident defect: 'no input block')",
            }]
        return []

    if archetype == "hybrid":
        if not present:
            return [{
                "reason": "hybrid archetype requires a 2-line Starting Points container -- "
                          "none found",
            }]
        if node_count != 2:
            return [{
                "reason": "hybrid archetype requires exactly 2 Starting Points nodes (an "
                          f"existing-format line + a from-scratch line), found {node_count}",
            }]
        return []

    return [{"reason": f"unrecognized archetype {archetype!r}"}]


def check_diagram_column_balance(markdown_text: str) -> list[dict]:
    """Hard gate (2026-08-08): up to 5 Core Capabilities lines use a single column; 6 or
    more must split into exactly 2 columns whose sizes differ by at most 1 (a "balanced"
    split). Returns a list of {"reason": ...} findings, empty if the layout is correct.
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []
    graph = parse_diagram(mermaid_text)
    total = sum(len(col) for col in graph.capability_columns)
    if total == 0:
        return [{"reason": "no capability nodes found"}]
    if total <= 5:
        if len(graph.capability_columns) != 1:
            return [{
                "reason": f"{total} capabilities should use exactly 1 column, "
                          f"found {len(graph.capability_columns)}"
            }]
        return []
    if len(graph.capability_columns) != 2:
        return [{
            "reason": f"{total} capabilities should split into exactly 2 balanced columns, "
                      f"found {len(graph.capability_columns)}"
        }]
    sizes = sorted(len(c) for c in graph.capability_columns)
    if sizes[1] - sizes[0] > 1:
        return [{"reason": f"columns not balanced: sizes {sizes}"}]
    return []


def check_diagram_known_subgraph_ids(markdown_text: str) -> list[str]:
    """Return any TOP-LEVEL `## At a glance` subgraph ID outside the canonical set
    {StartingPoints, Capabilities, Outputs}. A non-blocking tripwire. Nested column
    subgraphs used for the 2-column capability layout are expected to be non-canonical
    (e.g. `capl`/`capr`) and are deliberately not flagged -- only nesting depth 0 is
    checked. Returns [] if there's no mermaid block.
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []

    unknown = []
    depth = 0
    for raw_line in mermaid_text.splitlines():
        line = raw_line.strip()
        match = _SUBGRAPH_START_RE.match(line)
        if match:
            if depth == 0 and match.group(1) not in _CANONICAL_SUBGRAPH_IDS:
                unknown.append(match.group(1))
            depth += 1
            continue
        if _SUBGRAPH_END_RE.match(line):
            depth = max(0, depth - 1)
    return unknown


def check_diagram_matches_capability_dependencies(
    markdown_text: str, pipeline_edges: list[list[str]] | None
) -> list[dict]:
    """Hard gate once a product has a recorded pipeline_edges list (rewritten 2026-08-08:
    the pre-simplification diagram compared drawn EDGES against recorded edges; the
    simplified diagram has no per-capability edges left to compare, so this now compares
    COLUMN ORDER instead).

    `pipeline_edges` is the `[[from_capability_id, to_capability_id], ...]` value from a
    product's `data/diagram_capability_dependencies.json` entry, keyed to the CURRENT
    diagram's own node IDs (re-recorded during MT024 Phase 1 when a product's diagram is
    redrawn under the new model -- the old C1..C6b-style IDs from the pre-simplification
    per-node-edge diagrams no longer exist as separate nodes once siblings merge into one
    Core Capabilities line, so a stale pre-simplification pipeline_edges entry will report
    every pair as "capability_not_found" until re-recorded against the new node IDs; this
    is the intended fail-loud behavior, not a bug to silently work around). None means
    "never traced" (a no-op, correctly -- nothing recorded to contradict); [] means
    "traced, confirmed no dependencies" and is still checked (there's nothing to verify
    against an empty list, so it also returns [] in practice, but the distinction from
    None is preserved for the same reason diagram_archetypes.json's absence-semantics are).

    For every recorded [from, to] pair, `from` must appear at or before `to`'s position
    within `to`'s own column's node list -- an upstream capability must never be listed
    below the capability that depends on it, within the same column. Cross-column
    ordering is unconstrained (columns are independent visual tracks, not one strict
    sequence); a dependency between two capabilities in different columns is not itself
    a defect, so this only flags a same-column mis-ordering or a referenced ID that
    doesn't exist in either column at all.

    Findings, each a dict with a "type" key: "capability_not_found" (from/to isn't any
    known capability node) or "wrong_order" (from appears after to in the same column).
    """
    if not pipeline_edges:
        return []

    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []

    graph = parse_diagram(mermaid_text)
    position: dict[str, tuple[int, int]] = {}
    for col_idx, column in enumerate(graph.capability_columns):
        for row_idx, node_id in enumerate(column):
            position[node_id] = (col_idx, row_idx)

    findings: list[dict] = []
    for from_id, to_id in pipeline_edges:
        from_pos = position.get(from_id)
        to_pos = position.get(to_id)
        if from_pos is None or to_pos is None:
            findings.append({"type": "capability_not_found", "from": from_id, "to": to_id})
            continue
        if from_pos[0] == to_pos[0] and from_pos[1] > to_pos[1]:
            findings.append({
                "type": "wrong_order", "from": from_id, "to": to_id,
                "detail": f"{from_id} listed after {to_id} in the same column",
            })
    return findings


def check_diagram_hybrid_reverification(
    markdown_text: str, archetype_entry: dict | None, plan_run_date: str
) -> list[dict]:
    """Hard gate (2026-08-08, Rule 2 refinement #2; NARROWED 2026-08-08, Eleventh incident /
    MT025). A diagram may render a `Starting Points` container for a HYBRID-archetype product
    only when that classification has been freshly re-confirmed as part of THIS `plan` run,
    never silently carried forward from an old decision.

    Narrowed scope (MT025): this function used to ALSO hard-reject any Starting Points
    container found on a non-hybrid product ("archetype is 'X', not 'hybrid'" -> fail). Direct
    code investigation during the Eleventh-incident forensic pass confirmed this was the
    literal, coded mechanism blocking every attempt to add a real Starting Points container to
    a transform/compile-archetype product -- not a missing rule, an actively wrong one. That
    presence/absence/count responsibility now belongs entirely to
    check_diagram_starting_points_presence (archetype-general, covers all four archetypes).
    This function narrows to ONLY hybrid's own freshness/evidence requirement -- a no-op for
    every other archetype regardless of whether a Starting Points container is present, since
    presence-appropriateness is no longer this function's job.

    `archetype_entry` is the product's own matching row from `data/diagram_archetypes.json`
    (or None if no override entry exists -- absence defaults to `transform`). `plan_run_date`
    is the current run's own pinned date (`YYYY-MM-DD`). The 3-condition hybrid test itself
    (reads an existing format for editing AND has a dedicated from-scratch capability AND that
    capability takes real structured construction parameters) is unchanged from the Template
    section's original spec -- this check only enforces that its evidence citation is fresh,
    not the test itself, which stays real human/agent verification against current source.

    Returns a list of {"reason": ...} findings; empty when either no Starting Points container
    is present, the archetype isn't (recorded as) hybrid, or it is hybrid with fresh, evidenced
    classification.
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []
    graph = parse_diagram(mermaid_text)
    if "starting_points" not in graph.subgraph_kinds_seen:
        return []
    if archetype_entry is None or archetype_entry.get("archetype") != "hybrid":
        return []

    if not (archetype_entry.get("evidence") or "").strip():
        return [{"reason": "hybrid archetype entry has no evidence citation"}]
    if archetype_entry.get("decided_at") != plan_run_date:
        return [{
            "reason": f"hybrid archetype entry's decided_at "
                      f"({archetype_entry.get('decided_at')}) was not refreshed for this "
                      f"run ({plan_run_date}) -- re-verify the 3-condition hybrid test "
                      f"against real, current source before trusting this classification"
        }]
    return []


def check_diagram_format_support_claims(
    markdown_text: str, formats_md_text: str, known_format_names: set[str] | None = None
) -> list[dict]:
    """Hard gate (2026-08-08, Rule 2 refinement #1 -- "only add input/output formats which
    are actually supported"). Every recognized format token named anywhere in the At-a-
    glance diagram (Starting Points, Core Capabilities, or Outputs) must appear in this
    product's own `knowledge/{family}/{platform}/merged/formats.md` -- the same source
    `plan`'s factpack step already reads, so this is real reuse, not a new dependency.

    `known_format_names` is the canonical vocabulary used to recognize which diagram-label
    tokens are format claims at all (sourced from `data/format_descriptions.json`'s keys),
    distinguishing a real format claim from an ordinary word in a capability description.
    Distinct from `check_format_name_casing` (below) -- a format can be spelled with
    perfect canonical casing and still not be genuinely supported by this specific
    product; the two checks verify different properties and are not redundant.

    Returns a list of {"node_id", "label", "format", "reason"} findings for every format
    named in the diagram but absent from the verified formats list -- this plan's own
    single worst defect class (a fabricated capability claim), restated for format tokens.
    """
    known_format_names = known_format_names or set()
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []
    graph = parse_diagram(mermaid_text)

    findings = []
    for node_id, label in graph.node_label.items():
        kind = graph.node_subgraph.get(node_id)
        if kind not in ("starting_points", "capabilities", "outputs"):
            continue
        tokens = set(re.findall(r"[A-Za-z][A-Za-z0-9+]{1,9}", label))
        for token in tokens:
            canonical = next(
                (f for f in known_format_names if f.upper() == token.upper()), None
            )
            if canonical is None:
                continue
            if not re.search(rf"\b{re.escape(canonical)}\b", formats_md_text, re.IGNORECASE):
                findings.append({
                    "node_id": node_id, "label": label, "format": canonical,
                    "reason": f"'{canonical}' named in the diagram but not found in this "
                              f"product's verified formats.md",
                })
    return findings


def check_diagram_container_format_purity(
    markdown_text: str,
    container_kind: str,
    known_format_names: set[str] | None = None,
    connector_allowlist: set[str] | None = None,
) -> list[dict]:
    """Hard gate (2026-08-08, Eleventh incident / MT025, Rule B). Every Starting Points /
    Outputs node's CORE text (the part before its first parenthetical qualifier, if any) must
    tokenize entirely into: a recognized format name, a small connector-noun/article word, a
    version-number token, or (Starting Points only) the fixed hybrid literal "Nothing --
    authored from scratch". Anything else is flagged by name -- this is what "output block
    mentions a lot of other things where as it should be output formats only" (the user's own
    words, verbatim) becomes mechanically testable instead of a subjective judgment call.

    Distinct from check_diagram_format_support_claims (above): that function asks "if this
    node claims a KNOWN format, is it genuinely supported by this product" (accuracy); this
    function asks "is every node in this container a format claim AT ALL, and nothing else"
    (purity/membership). A label like "Traversable DOM document tree" never trips the accuracy
    check (none of its tokens match any known format name, so it's silently skipped there) but
    fails this one outright -- exactly the gap that let 6 of 10 sampled products' Outputs
    containers mix real formats with non-format capability-return descriptions (extracted
    data, in-memory object graphs, QA reports, API-response framing) while every existing check
    reported 100% PASS.

    Parenthetical qualifiers are deliberately NOT checked -- validated directly against the
    real corpus that motivated this check: every legitimate qualifier found there (`"(file path
    or binary stream)"`, `"(widths, kerning, ligatures)"`, `"(including encrypted)"`) sits
    inside parens, and every real violation found in the 2026-08-08 investigation fails on its
    core text alone, so constraining only the core avoids false-positiving on legitimate
    supplementary detail.

    `container_kind` is `"starting_points"` or `"outputs"`. `known_format_names` should be the
    union of `check_diagram_format_support_claims`'s vocabulary (`data/format_descriptions.
    json`'s keys) and `_DIAGRAM_SUPPLEMENTARY_FORMAT_NAMES` (below) -- confirmed necessary by
    this check's own 2026-08-08 sanity pass against all 30 real candidates: `format_descriptions
    .json` alone is missing several formats this portfolio genuinely produces (PPTX, CFB, MSG,
    EML, STL, OBJ, GLTF, ...), which would otherwise make this a hard gate that blocks
    already-correct content. A trailing plural "s" is stripped before matching (`"PDFs"` ->
    `"PDF"`) -- found live in `pdf/python`'s real, correct "Encrypted PDFs" node, which would
    otherwise false-positive on exact-match alone. `connector_allowlist` defaults to
    `_CONTAINER_CONNECTOR_ALLOWLIST` -- a seed list, explicitly not claimed complete; expect
    real additions as Phase 1/2 execution reaches products outside the original sample (see the
    plan's "Tradeoffs, risks, and honest limits").

    Returns a list of {"node_id", "label", "container", "unrecognized_tokens"} findings, empty
    if every node in the given container is format-pure.
    """
    known_format_names = known_format_names or set()
    connector_allowlist = connector_allowlist or _CONTAINER_CONNECTOR_ALLOWLIST
    format_upper = {f.upper() for f in known_format_names}

    def _is_known_format(token: str) -> bool:
        upper = token.upper()
        if upper in format_upper:
            return True
        if upper.endswith("S") and upper[:-1] in format_upper:
            return True
        return False

    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []
    graph = parse_diagram(mermaid_text)

    findings = []
    for node_id, kind in graph.node_subgraph.items():
        if kind != container_kind:
            continue
        label = graph.node_label.get(node_id, "")
        if container_kind == "starting_points" and _HYBRID_FROM_SCRATCH_RE.match(label.strip()):
            continue
        core = label.split("(", 1)[0].strip()
        unrecognized = []
        for token in _PURITY_TOKEN_RE.findall(core):
            if _is_known_format(token):
                continue
            if token.lower() in connector_allowlist:
                continue
            if _VERSION_TOKEN_RE.match(token):
                continue
            unrecognized.append(token)
        if unrecognized:
            findings.append({
                "node_id": node_id, "label": label, "container": container_kind,
                "unrecognized_tokens": unrecognized,
            })
    return findings


def check_diagram_format_completeness_hint(
    markdown_text: str, formats_md_text: str, archetype: str
) -> list[dict]:
    """Heuristic, non-blocking (2026-08-08, Eleventh incident / MT025). Cross-references
    formats.md's Import=Yes / Export=Yes rows against the diagram's Starting Points / Outputs
    node text and flags a real, supported format with zero mention anywhere in the
    corresponding container -- the `3d/net` gap found during this investigation (10
    import-capable formats recorded in formats.md, 0 shown as diagram inputs before this fix).

    Deliberately heuristic, never a hard gate: `formats.md` is confirmed unreliable in at least
    one real case (`tex/python`'s PDF/DVI/SVG rows are all marked Export=No despite the product
    genuinely producing all three, per its own README and diagram) -- a hard gate here would
    sometimes fail an honestly-correct diagram over stale source data, which this plan has never
    done to any other check keyed off a source already known to have real staleness.

    Returns a list of {"format", "container", "reason"} findings.
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None or not formats_md_text:
        return []
    graph = parse_diagram(mermaid_text)

    def _container_text(kind: str) -> str:
        return " ".join(
            label for node_id, label in graph.node_label.items()
            if graph.node_subgraph.get(node_id) == kind
        )

    starting_text = _container_text("starting_points").upper()
    outputs_text = _container_text("outputs").upper()

    findings = []
    for row_match in re.finditer(
        r"^\|\s*([A-Za-z0-9_.+-]+)\s*\|\s*(Yes|-)\s*\|\s*(Yes|-)\s*\|",
        formats_md_text, re.MULTILINE,
    ):
        fmt = row_match.group(1).upper()
        import_flag, export_flag = row_match.group(2), row_match.group(3)
        if archetype != "generative" and import_flag == "Yes" and fmt not in starting_text:
            findings.append({
                "format": fmt, "container": "starting_points",
                "reason": f"formats.md marks {fmt} Import=Yes but it is not named in the "
                          "Starting Points container",
            })
        if export_flag == "Yes" and fmt not in outputs_text:
            findings.append({
                "format": fmt, "container": "outputs",
                "reason": f"formats.md marks {fmt} Export=Yes but it is not named in the "
                          "Outputs container",
            })
    return findings


def check_only_mermaid_block_changed(old_markdown_text: str, new_markdown_text: str) -> bool:
    """Return True iff the only difference between old and new is inside the
    ```mermaid ... ``` fenced block (fences included).

    Both texts have their fenced mermaid block (if any) replaced with an
    identical fixed placeholder, then compared for exact equality. If a text
    has no mermaid block, the placeholder substitution is a no-op for it --
    so a mermaid block appearing/disappearing between old and new correctly
    fails this check (that is not "only the diagram changed").
    """
    old_stripped = _MERMAID_BLOCK_FULL_RE.sub(_MERMAID_BLOCK_PLACEHOLDER, old_markdown_text, count=1)
    new_stripped = _MERMAID_BLOCK_FULL_RE.sub(_MERMAID_BLOCK_PLACEHOLDER, new_markdown_text, count=1)
    return old_stripped == new_stripped


# 2026-08-08: handles the "badge" pattern -- [![alt](img-url)](link-url), used at the top of
# nearly every README in this portfolio for CI/license/contributor badges -- as well as a
# plain [text](target) link. A real bug found via a sub-agent's own investigation of a
# check_format_name_casing false positive on html/python: the original pattern's
# `[^\]]*` greedily stopped at the FIRST `]`, which for a badge is the INNER image alt
# text's own closing bracket, not the outer link's -- the regex then matched only the
# inner `![alt](img-url)` as if it were the whole link, leaving the real OUTER href
# (containing the repo slug, e.g. "aspose-html-foss") completely unmatched and therefore
# never stripped before prose scanning. The alternation lets a nested `![...](...)` be
# consumed as one unit before the real closing `]`, so group(2) is always the real,
# outermost href. Group(1) ("anchor text") is the badge's own `![alt](img-url)` markdown
# for a badge link (not real visible text, but never coincidentally matches a phrase like
# "Enterprise Edition" either, so existing anchor-text callers stay correct) or the real
# visible text for a plain link, unchanged from before.
_MD_LINK_RE = re.compile(r"\[((?:!\[[^\]]*\]\([^)]*\)|[^\]])*)\]\(([^)\s]+)\)")
# "Additional examples" deliberately excluded: the Template section makes it vacuously
# optional ("If a product has no 'Additional examples' section at all (too few real snippets
# to justify one), this requirement is vacuously satisfied") -- confirmed real, not
# hypothetical: cells/cpp is the one product in the current 30-file portfolio with no such
# section, and it is not a defect. "Enough real snippets to justify one" is a content-quality
# judgment call this check cannot responsibly automate, so it stays outside the hard gate.
# 2026-08-08 (Rule 6): title-cased to match check_heading_title_case -- these two hard gates
# must agree on the canonical heading text, or they directly contradict each other (one
# requiring exact sentence-case text, the other requiring title case). A real bug found
# via this module's own test suite when check_heading_title_case landed: the old sentence-
# case list here silently stopped matching once a fixture's headings were title-cased.
_REQUIRED_SECTIONS = [
    "At a Glance",
    "Key Capabilities",
    "Installation",
    "Quick Start",
    "API Reference",
    "Documentation & Resources",
    "Scope and Limitations",
    "Development and Testing",
    "License",
]
_ASPOSE_LINK_HOST_RE = re.compile(r"https?://(?:[\w-]+\.)*aspose\.(?:org|com)\b")
_ENTERPRISE_LINK_HOST_RE = re.compile(r"https?://(?:[\w-]+\.)*products\.aspose\.com\b")


def compute_link_caps(readme_text: str) -> dict:
    """Count markdown links by category for the link-density-ceiling rule (Template section,
    "no repeated Enterprise mention... to respect the link-density ceiling").

    Returns {"total_links", "aspose_org_links", "enterprise_edition_links",
    "enterprise_edition_link_contexts"} -- the last is a list of ~60-char text snippets
    surrounding each Enterprise link, so a caller can confirm every one is confined to the
    Scope and limitations section without re-parsing the file.
    """
    links = _MD_LINK_RE.findall(readme_text)
    total = len(links)
    aspose_org = sum(1 for _, href in links if _ASPOSE_LINK_HOST_RE.search(href))
    enterprise_contexts = []
    for match in re.finditer(_MD_LINK_RE, readme_text):
        href = match.group(2)
        if _ENTERPRISE_LINK_HOST_RE.search(href):
            start = max(0, match.start() - 30)
            end = min(len(readme_text), match.end() + 30)
            enterprise_contexts.append(readme_text[start:end].replace("\n", " "))
    return {
        "total_links": total,
        "aspose_org_links": aspose_org,
        "enterprise_edition_links": len(enterprise_contexts),
        "enterprise_edition_link_contexts": enterprise_contexts,
    }


def count_aspose_links(readme_text: str) -> int:
    """Count markdown links whose href targets an aspose.org or aspose.com subdomain."""
    return sum(
        1 for _, href in _MD_LINK_RE.findall(readme_text) if _ASPOSE_LINK_HOST_RE.search(href)
    )


# 2026-08-08: order-agnostic (was qualifier-then-target only). A real, live false positive
# found via portfolio inventory: 3d/net's real, already-correct sentence -- "For proprietary
# formats (A3DW, PDF, USD, JT), rendering, and advanced mesh operations, see [...]" -- has
# the target-class word ("formats") appear BEFORE the qualifier ("advanced"), which natural
# English sentences do about as often as the reverse order; a directional-only regex missed
# this real, well-written explanation entirely.
_QUALIFIER_WORD = r"\b(?:broader|full|complete|additional|advanced|commercial)\b"
_FUNCTIONALITY_WORD = r"\b(?:functionality|feature|format|support|coverage|capabilit)"
_BROADER_FUNCTIONALITY_CONTEXT_RE = re.compile(
    rf"{_QUALIFIER_WORD}.{{0,80}}{_FUNCTIONALITY_WORD}|{_FUNCTIONALITY_WORD}.{{0,80}}{_QUALIFIER_WORD}",
    re.IGNORECASE | re.DOTALL,
)


def check_enterprise_edition_naming(readme_text: str) -> list[dict]:
    """Two checks in one, both against every `products.aspose.com` link found:

    1. **Naming** (as before): the visible anchor text must contain "Enterprise Edition" --
       the decided, single portfolio-wide standard (2026-08-08, via AskUserQuestion,
       matching this function's own name; deliberately not `backlink_targets.py`'s
       "Enterprise Product"/"Enterprise Product Family" phrasing, a different convention
       for a different consumer: docs/kb/reference/products pages, not GitHub READMEs).
       Confirmed live 3-way drift across a 6-file sample this decision closes: "Enterprise
       Edition" (majority), "Enterprise Product" (`pdf/cpp`, `cells/cpp`), and no qualifier
       at all (`words/net`, a real gap).
    2. **Context** (2026-08-08, Rule 4 -- "the anchor explains access to broader/full
       product functionality, rather than using a naked brand or promotional CTA"): the
       ~120 characters surrounding the link must contain language explaining what broader
       functionality is gained (a `broader`/`full`/`complete`/`additional`/`advanced`/
       `commercial` word near a `functionality`/`feature`/`format`/`support`/`coverage`/
       `capability` word) -- distinguishing a real explanatory sentence from a bare "See
       [Enterprise Edition](...)" CTA with no stated reason to click.

    Findings carry a "reason" of "missing_naming", "missing_context", or both (as separate
    findings) so a caller can tell which half failed. Hard gate for naming (mechanically
    unambiguous once the standard is decided); the context half stays a heuristic prompt,
    since "does this sentence really explain the value" is a content-quality judgment call.
    """
    findings = []
    for match in _MD_LINK_RE.finditer(readme_text):
        anchor_text, href = match.group(1), match.group(2)
        if not _ENTERPRISE_LINK_HOST_RE.search(href):
            continue
        if "Enterprise Edition" not in anchor_text:
            findings.append({
                "anchor_text": anchor_text, "href": href, "reason": "missing_naming",
                "detail": 'anchor text must contain "Enterprise Edition"',
            })
        # Paragraph-aware window (2026-08-08 fix): a real, significant false-positive source
        # found via live inventory against all 30 products -- a fixed 60-char-before lookback
        # is centered on the LINK, not the SENTENCE, so it routinely cuts off the qualifying
        # word in real, already-well-written explanatory sentences (e.g. "For rendering, the
        # broader exchange-format set (FBX, glTF, USD, PDF, JT, and more), and advanced mesh
        # operations, see [Aspose.3D for Java Enterprise Edition](...)." -- "broader" sits ~90
        # characters before the link, well outside the old 60-char window). Look back to the
        # nearest paragraph boundary (blank line) instead, capped generously so one giant
        # paragraph can't pull in unrelated prior content.
        para_start = readme_text.rfind("\n\n", 0, match.start())
        start = max(0, match.start() - 400, (para_start + 2) if para_start != -1 else 0)
        end = min(len(readme_text), match.end() + 100)
        context = readme_text[start:end].replace("\n", " ")
        if not _BROADER_FUNCTIONALITY_CONTEXT_RE.search(context):
            findings.append({
                "anchor_text": anchor_text, "href": href, "reason": "missing_context",
                "detail": "surrounding text doesn't explain the broader/full functionality gained",
                "context": context,
            })
    return findings


def check_required_sections(readme_text: str) -> list[str]:
    """Return the list of required H2 section names missing from the README. Hard gate --
    every product's candidate must carry the full Template section list, always."""
    missing = []
    for section in _REQUIRED_SECTIONS:
        if not re.search(rf"^##\s+{re.escape(section)}\s*$", readme_text, re.MULTILINE):
            missing.append(section)
    return missing


def surgical_diff_check(declared_file_set: list[str], changed_files: list[str]) -> list[str]:
    """Return any path in changed_files not present in declared_file_set -- an undeclared
    change. Hard gate at push time: the file set is fixed at plan time and shown during
    review (Design section, "surgical_diff_check (declared file-set only...)"); anything
    outside it must never silently ride along in the same push.
    """
    declared = set(declared_file_set)
    return [path for path in changed_files if path not in declared]


def check_license_link_target(readme_text: str, clone_cache_root: str) -> list[dict]:
    """Verify the ## License section's link target (if any) exists on disk, case-sensitively,
    under clone_cache_root. Hard gate -- catches both a fabricated path (words/python's real
    License/license.txt vs the candidate's claimed License/license.txt casing/name mismatch)
    and a missing-license-file case that should carry no link at all (3d/typescript).

    Returns [] when the section either has no link (plain-text "MIT License", the correct
    form when no license file exists) or the linked path resolves case-sensitively on disk.
    Returns a one-item list with the bad target when the link is present but doesn't resolve.
    """
    license_match = re.search(r"^##\s+License\s*$(.*?)(?=^##\s|\Z)", readme_text, re.MULTILINE | re.DOTALL)
    if not license_match:
        return []
    section_text = license_match.group(1)
    link_match = _MD_LINK_RE.search(section_text)
    if not link_match:
        return []
    target = link_match.group(2)
    if target.startswith(("http://", "https://")):
        return []
    root = Path(clone_cache_root)
    candidate = root / target
    if candidate.is_file():
        try:
            real_name = next(p.name for p in candidate.parent.iterdir() if p.name == candidate.name)
        except StopIteration:
            real_name = None
        if real_name != candidate.name:
            return [{"target": target, "reason": "case mismatch on disk"}]
        return []
    return [{"target": target, "reason": "target does not exist under clone cache"}]


_PROCESS_NARRATION_PATTERNS = [
    r"\bat the time of writing\b",
    r"\bas of this writing\b",
    r"\bconsult the repository directly\b",
    r"\bas declared in\b",
    r"\bseems to\b",
    r"\bpresumably\b",
    r"\bpasses cleanly\b",
    r"\bcurrently fails\b",
    r"\bwas verified\b",
    r"\bverified with\b",
    r"\bverified against\b",
    r"\bconfirmed against this checkout\b",
    r"\bno match under\b",
    r"\bfound directly in source\b",
    r"\breproduced independently\b",
    r"\bthis reproduces with\b",
    r"\bfails identically\b",
    r"\breproduced from its own\b",
    r"\bthe upstream repository'?s own\b",
    r"\bthe source repository\b",
    r"\(per the\b",
    r"\bwithout obscuring the primary\b",
    # 2026-08-08 (Rule 3): broadened past the original 22 incident-specific literal
    # phrases into four named categories the rule calls out explicitly -- internal
    # receipts, execution notes, provenance, and confidence language -- rather than
    # only ever growing this list one past incident at a time.
    r"\baccording to (?:our|this) (?:audit|scan|sweep|review|analysis)\b",  # internal receipts
    r"\b(?:this|the) (?:session|run|pass) (?:found|confirmed|verified|checked)\b",  # execution notes
    r"\bgenerated (?:by|from|via) (?:the|this) (?:pipeline|skill|script|tool)\b",  # provenance
    r"\bwe (?:confirmed|verified|checked|found) that\b",  # confidence language
    r"\bhas been (?:verified|confirmed|validated) to\b",  # confidence language
]
_PROCESS_NARRATION_RE = re.compile("|".join(_PROCESS_NARRATION_PATTERNS), re.IGNORECASE)


def check_process_narration_smells(readme_text: str) -> list[dict]:
    """HARD GATE as of 2026-08-08 (Rule 3: "verification facts... never leak into
    visitor-facing prose... internal receipts, execution notes, provenance, and confidence
    language are blocked") -- elevated from its original heuristic status, a materially
    stronger requirement than the prior "surfaced for judgment" framing. Flags sentences
    narrating the generation/verification *process*, an internal receipt, an execution
    note, a provenance citation, or confidence-language about the README's own accuracy,
    instead of stating a plain product fact (Template section, "No process/investigation-
    log narration anywhere in the README"). A plain present-tense limitation sentence in
    Scope and limitations is fine; the smell is the audit-trail *voice*, not the presence
    of a caveat -- "useful limitations are rewritten as user guidance" per Rule 3, not
    deleted.
    """
    findings = []
    for match in _PROCESS_NARRATION_RE.finditer(readme_text):
        start = max(0, match.start() - 40)
        end = min(len(readme_text), match.end() + 40)
        findings.append({"phrase": match.group(0), "context": readme_text[start:end].replace("\n", " ")})
    return findings


# 2026-08-08: the language tag is now MANDATORY (was optional). A real, significant bug
# found via this module's own test suite once a real Mermaid diagram was added ahead of an
# Installation section's bash block (now true of every README under the 2026-08-08
# simplified diagram model, which requires an ## At a Glance diagram on every product):
# with the tag optional, the regex failed to match the ```mermaid opening fence (since
# "mermaid" isn't a recognized tag), then incorrectly treated the mermaid block's own
# UNTAGGED closing "```\n" as a fresh opening fence for an untagged block, silently
# swallowing everything up to the *next* ``` as "code content" and desyncing every match
# after it -- the real ```bash blocks were never found at all. Requiring the tag means an
# untagged/other-language fence (like mermaid's own closing ```) can never be mistaken for
# an opening delimiter. Also adds "cmake" -- C++ products' real Installation/Development
# sections use ```cmake fenced blocks, which this hard gate had never recognized before.
_FENCED_CODE_RE = re.compile(r"```(?:bash|sh|shell|powershell|cmd|cmake)\n(.*?)```", re.DOTALL)
_BLOCKING_ISSUE_RE = re.compile(
    r"-\s+\*\*Severity\*\*:\s*BLOCKING.*?-\s+\*\*Evidence\*\*:\s*(.+?)\n",
    re.DOTALL,
)


def check_no_undisclosed_blocking_commands(readme_text: str, upstream_issues_text: str) -> list[dict]:
    """Cross-check every fenced install/build command in the README against upstream-issues.md's
    BLOCKING-severity entries for that exact command. Hard gate -- the html/python and words/net
    incidents (a documented BLOCKING command shipped as the standard Installation step, with no
    warning) were a correctness/safety defect, not a style one, so this one blocks the
    transition rather than just prompting review.
    """
    blocking_commands = []
    for match in _BLOCKING_ISSUE_RE.finditer(upstream_issues_text):
        evidence = match.group(1).strip().strip("`")
        blocking_commands.append(evidence)
    if not blocking_commands:
        return []
    findings = []
    for code_match in _FENCED_CODE_RE.finditer(readme_text):
        block = code_match.group(1)
        for blocking_cmd in blocking_commands:
            if blocking_cmd and blocking_cmd in block:
                findings.append({"command": blocking_cmd, "block": block.strip()})
    return findings


_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.MULTILINE)


_INTERNAL_LABEL_PATTERNS = [
    r"\bpreserved repository details\b",
    r"\bdropped claims?\b",
    r"\bcarried forward from (?:the )?old readme\b",
    r"\bverification status\b",
    r"\bdisposition\b",
    r"\bcandidate readme\b",
    r"\bthis readme(?:'s)? (?:generation|generated)\b",
]
_INTERNAL_LABEL_RE = re.compile("|".join(_INTERNAL_LABEL_PATTERNS), re.IGNORECASE)


def check_dropped_content(old_readme_text: str, new_readme_text: str, clone_cache_root: str) -> dict:
    """Diff the old (upstream) README against the new candidate for links and H2/H3 headings
    present in the old file with no match anywhere in the new one. Hard gate at
    ingest-candidate -- a flagged item needs an explicit disposition in dropped_claims.json
    (carried forward / dropped with a verified reason) before the transition can pass, per
    the "Never drop original-README content without a verified reason" rule.

    Returns {"dropped_links": [...], "dropped_headings": [...], "internal_labels": [...]}.
    A link is "dropped" only if its exact target string doesn't appear anywhere in
    new_readme_text (a real move to a different section still counts as carried forward,
    correctly). clone_cache_root is accepted for API-shape parity with
    check_license_link_target (a caller may wish to filter out links to files that no
    longer exist upstream either) but this heuristic-diff pass does not itself require it
    to detect a drop.

    `internal_labels` is the 2026-08-08 (Rule 7) addition -- "meaning is preserved... but
    internal labels such as 'Preserved repository details' are forbidden" -- a hard-gate
    scan of new_readme_text for meta/process labels that describe the README's OWN
    generation or internal bookkeeping rather than the product itself (a heading or bullet
    reading "Preserved repository details", "Dropped claims", "Verification status", etc.).
    This closes the loophole where the meaning-preservation half of Rule 7 (already covered
    by dropped_links/dropped_headings above) could technically pass while the preserved
    content was labeled with exactly this kind of internal, non-visitor-facing language.
    """
    del clone_cache_root  # accepted for signature parity; presence-diffing needs only the two texts
    old_links = {href for _, href in _MD_LINK_RE.findall(old_readme_text) if not href.startswith(("http://", "https://"))}
    dropped_links = sorted(href for href in old_links if href not in new_readme_text)

    old_headings = {m.group(2) for m in _HEADING_RE.finditer(old_readme_text)}
    new_headings_and_body = new_readme_text
    dropped_headings = sorted(h for h in old_headings if h not in new_headings_and_body)

    internal_labels = sorted({m.group(0) for m in _INTERNAL_LABEL_RE.finditer(new_readme_text)})

    return {
        "dropped_links": dropped_links,
        "dropped_headings": dropped_headings,
        "internal_labels": internal_labels,
    }


_EXCLUDED_DOMAINS_RE = re.compile(r"https?://(?:[\w-]+\.)*(?:forum\.aspose\.com|[\w-]+\.aspose\.app)\b")


def check_no_excluded_domain_links(readme_text: str) -> list[str]:
    """Hard gate: reject any link whose host is forum.aspose.com or matches *.aspose.app --
    a standing policy ("we will not link to forum.aspose.com or any subdomain at aspose.app
    at this stage"), not a per-run judgment call. Returns the list of matched URLs.
    """
    return [m.group(0) for m in _EXCLUDED_DOMAINS_RE.finditer(readme_text)]


_CLASS_BULLET_RE = re.compile(
    r"^(?P<indent> *)-\s+`([A-Za-z_][\w.]*)`(?:\s*/\s*`([A-Za-z_][\w.]*)`)?(?:\s*[—-]+.*)?$",
    re.MULTILINE,
)
_BACKTICK_MEMBER_RE = re.compile(r"`([A-Za-z_]\w*(?:\([^)]*\))?)`")
_SUB_BULLET_LINE_RE = re.compile(r"^ +-\s+(.+)$")


def check_named_member_accuracy(readme_text: str, clone_cache_root: str) -> list[dict]:
    """Heuristic accuracy check for the API reference's real on-disk bullet convention: a
    top-level `` - `ClassName` [— description] `` bullet followed by zero or more MORE-INDENTED
    sub-bullet lines listing that class's real members (either one signature per line, e.g.
    `` - `create(subject, body) -> "MapiMessage"` ``, or a single `properties: `a`, `b`, `c`
    ``-style comma line) -- does every member named in those sub-bullets plausibly exist on the
    named class's real source?

    Deliberately does NOT treat a bare single-line "`ClassName` — prose mentioning `a_term()`"
    bullet (no indented sub-bullets following it, e.g. an Exceptions-list one-liner) as a
    member-list claim -- confirmed via a real false-positive during this function's own
    development (barcode/python's "`SymbologyNotFoundError` — unknown symbology name passed to
    `generate()`" is a description, not a claim that `generate()` is SymbologyNotFoundError's
    own member; only genuinely indented sub-bullets count as the member list).

    HONEST SCOPE STATEMENT (do not treat a clean pass from this function as compiler-grade
    proof): this is a grep-based heuristic, not the full per-language extraction the plan's
    Verification pass section describes (`javap -public` for Java, real introspection for
    Python, compiler diagnostics for C#/Go/Rust/C++, `tsc` for TypeScript). It locates
    candidate source files for a named class via a simple `class ClassName`/`struct
    ClassName`/`interface ClassName` grep across clone_cache_root, then checks whether each
    named member token appears anywhere in that file's text. This can miss real member-name
    typos hidden by fuzzy matching, can under-report on classes split across multiple files
    (partial classes, extension methods, trait impls), and does NOT trace inheritance -- a
    member declared once on a base class and inherited (confirmed live: words/net's
    `Document.GetText()`, real and callable, declared only on the base `Node` class) will be
    flagged as "not found" even though it's genuinely valid. A member absent from every
    candidate file is a real, worth-flagging signal, but presence in the file text is not proof
    the member is real, public, and matches the exact bullet's claimed shape. Treat every
    finding as a prompt for the same real per-language verification this check cannot fully
    automate, never as a substitute for it.

    Returns a list of {"class_name", "member", "reason"} findings for members not found in any
    candidate source file for their class. Returns [] (not an error) if a class name has zero
    candidate source files -- that's a "couldn't verify" case for the human/agent pass, not a
    fabrication claim this heuristic can respons­ibly make on no evidence.
    """
    root = Path(clone_cache_root)
    if not root.is_dir():
        return []

    lines = readme_text.splitlines()
    findings = []
    for match in _CLASS_BULLET_RE.finditer(readme_text):
        class_a, class_b = match.group(2), match.group(3)
        bullet_indent = len(match.group("indent"))
        bullet_line_idx = readme_text.count("\n", 0, match.start())

        members: list[str] = []
        for line in lines[bullet_line_idx + 1:]:
            sub_match = _SUB_BULLET_LINE_RE.match(line)
            if not sub_match:
                break
            sub_indent = len(line) - len(line.lstrip(" "))
            if sub_indent <= bullet_indent:
                break
            members.extend(_BACKTICK_MEMBER_RE.findall(sub_match.group(1)))
        if not members:
            continue

        for class_name in filter(None, (class_a, class_b)):
            candidate_files = _find_class_source_files(root, class_name)
            if not candidate_files:
                continue  # no evidence either way -- not a fabrication claim, skip silently
            combined_text = "\n".join(f.read_text(encoding="utf-8", errors="ignore") for f in candidate_files)
            for member in members:
                member_token = member.split("(")[0].split(":")[0].strip()
                if member_token and member_token not in combined_text:
                    findings.append({
                        "class_name": class_name,
                        "member": member,
                        "reason": f"not found in {len(candidate_files)} candidate source file(s)",
                    })
    return findings


def _find_class_source_files(root: Path, class_name: str, max_files: int = 5) -> list[Path]:
    """Locate up to max_files real source files plausibly DEFINING class_name (not merely
    forward-declaring it), via a cheap grep-style scan -- not a real per-language parse.
    Skips common non-source directories.

    The `(?!\\s*;)` negative lookahead is load-bearing, not decorative: a real bug found
    during this function's own development -- `class Worksheet;` forward declarations (C++
    headers routinely forward-declare a type before using it by reference/pointer) matched the
    same naive "class ClassName" regex as the real `class Worksheet final { ... }` definition,
    and since several forward-declaring headers sort alphabetically before the real definition
    file, they filled max_files before the real file was ever reached -- producing false
    "member not found" findings for members that are genuinely declared, just in a file this
    function never got to.
    """
    declare_re = re.compile(
        rf"\b(?:class|struct|interface|def)\s+{re.escape(class_name)}\b(?!\s*;)"
    )
    skip_dirs = {".git", "node_modules", "__pycache__", "target", "build", "dist", "bin", "obj"}
    found: list[Path] = []
    for path in root.rglob("*"):
        if len(found) >= max_files:
            break
        if not path.is_file() or path.suffix not in {
            ".py", ".java", ".cs", ".go", ".rs", ".cpp", ".hpp", ".h", ".ts", ".c"
        }:
            continue
        if skip_dirs & set(path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if declare_re.search(text):
            found.append(path)
    return found


_API_REF_INTRO_BAD_A_RE = re.compile(r"ships \d+ public types\.\s*Selected entry points:", re.IGNORECASE)
_API_REF_INTRO_BAD_B_RE = re.compile(r"`\w[\w.]*\.\*`?\s*\.?\s*$")
_API_REF_SECTION_RE = re.compile(
    r"^##\s+API reference\s*$(.*?)(?=<details>|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE
)


def check_api_reference_intro_names_classes(readme_text: str) -> bool:
    """Flag the "## API reference" intro sentence (text between the H2 heading and its
    <details> fold) when it matches either confirmed bad form: a bare "ships N public types.
    Selected entry points:" filler, or a bare trailing `namespace.*`/`package.*` wildcard with
    no backtick-quoted class name elsewhere in the sentence. Heuristic -- a hit is a prompt for
    the mandatory judgment pass to rewrite the sentence naming the product's real hub class(es),
    never an automatic fail (naming a real hub class is a content-quality judgment call).
    """
    section_match = _API_REF_SECTION_RE.search(readme_text)
    if not section_match:
        return False
    intro = section_match.group(1)
    if _API_REF_INTRO_BAD_A_RE.search(intro):
        return True
    if _API_REF_INTRO_BAD_B_RE.search(intro.strip()):
        # Only a defect if no OTHER backtick-quoted class name appears earlier in the sentence.
        other_backticks = _BACKTICK_MEMBER_RE.findall(intro)
        if len(other_backticks) <= 1:
            return True
    return False


_DELIVERY_MECHANISM_KEYWORDS_RE = re.compile(
    r"\b(?:path|stream|buffer|bytes|in-memory)\b", re.IGNORECASE
)
_WORD_RE = re.compile(r"[A-Za-z]{4,}")
# Generic/structural nouns that recur across genuinely-different Output labels (".msg files" vs
# ".eml files") -- excluded from "shared significant word" consideration so a coincidental shared
# noun alone never triggers this heuristic; the real 2026-08-05 incidents (cells/cpp, cells/rust)
# shared a specific format token (".xlsx workbook"), not a generic container word.
_GENERIC_LABEL_WORDS = {
    "file", "files", "document", "documents", "object", "objects", "data", "content",
    "contents", "output", "outputs", "format", "formats", "with", "from", "into",
}


def check_diagram_no_mechanism_duplicate_output(markdown_text: str) -> list[dict]:
    """Heuristic pre-filter for the "never split one output artifact into multiple Output
    nodes purely by delivery mechanism" rule (the cells/cpp and cells/rust incident). Flags
    any pair of Outputs-subgraph nodes whose labels share a significant word (>=4 letters) and
    where at least one label contains a delivery-mechanism keyword, while their inbound
    Capability-edge sets differ. A hit prompts the mandatory judgment pass ("same artifact,
    different mechanism" vs. "genuinely different content"), never an automatic fail -- several
    genuinely-different-content near-misses (3d/net's OBJ/STL/glTF vs FBX/COLLADA/3MF pair,
    among others) were checked and correctly left alone during the incident this exists to
    catch, so a hit here is not itself proof of a defect.
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []
    graph = parse_diagram(mermaid_text)

    output_nodes = [nid for nid, kind in graph.node_subgraph.items() if kind == "outputs"]
    inbound: dict[str, set] = {nid: set() for nid in output_nodes}
    for a, b in graph.edges:
        if b in inbound:
            inbound[b].add(a)

    findings = []
    for i, node_a in enumerate(output_nodes):
        label_a = graph.node_label.get(node_a, "")
        words_a = {w.lower() for w in _WORD_RE.findall(label_a)} - _GENERIC_LABEL_WORDS
        has_mechanism_a = bool(_DELIVERY_MECHANISM_KEYWORDS_RE.search(label_a))
        for node_b in output_nodes[i + 1:]:
            label_b = graph.node_label.get(node_b, "")
            words_b = {w.lower() for w in _WORD_RE.findall(label_b)} - _GENERIC_LABEL_WORDS
            has_mechanism_b = bool(_DELIVERY_MECHANISM_KEYWORDS_RE.search(label_b))
            shared_words = words_a & words_b
            if shared_words and (has_mechanism_a or has_mechanism_b) and inbound[node_a] != inbound[node_b]:
                findings.append({
                    "node_a": node_a, "label_a": label_a,
                    "node_b": node_b, "label_b": label_b,
                    "shared_words": sorted(shared_words),
                })
    return findings


_BARE_WORD_RE = re.compile(r"(?<![./\w])([A-Za-z]{2,10})\b")
# Generic project/doc acronyms that are NOT format names but routinely appear all-caps
# somewhere in a README (a repo name, a link target, a directory name) and in ordinary
# lowercase prose elsewhere -- confirmed real noise via this function's own 30-product
# portfolio test run: "FOSS" (29/30 files, from things like the `aspose-pdf-foss` org/repo
# slug and `aspose_pdf_foss` CMake target names) and "LICENSE" (from the bare filename,
# even after stripping link targets/inline-code -- e.g. "see the LICENSE file" in plain
# prose) together accounted for nearly every finding, drowning out genuine format-casing
# defects (COLLADA, PDF, HTML) in noise. Same stoplist pattern already established for
# check_diagram_no_mechanism_duplicate_output's _GENERIC_LABEL_WORDS.
_GENERIC_ACRONYM_STOPLIST = {
    "FOSS", "LICENSE", "API", "CLI", "URL", "SDK", "README", "CI", "FAQ", "TODO",
    "GUI", "MIT", "OSI", "ID",
}
# A different, narrower kind of exception (2026-08-08, found live in 3d/python/3d/typescript
# after a portfolio-wide diagram-redraw + heading-title-case pass): a format whose real,
# official canonical spelling is genuinely mixed-case (glTF, styled by the Khronos Group
# the same way "iPhone"/"eBay" are -- a lowercase leading letter is the *correct* form, not
# a defect) collides with Rule 6's mechanical title-case-every-heading requirement, which
# cannot represent that spelling inside a heading at all. The resolution applied portfolio-
# wide: "glTF" everywhere in prose/code/diagram labels (its real canonical form), "GLTF"
# (all-caps) only where it's the first word of a title-cased heading -- a deliberate,
# narrow, single-word exception, not an unnoticed inconsistency. Format names listed here
# are exempt from the "multiple different casings" finding specifically for the GLTF/glTF
# pair; any OTHER casing variant of the same word (e.g. "Gltf", "gltf" in prose) is still a
# real defect and still flagged.
_KNOWN_HEADING_CASE_EXCEPTIONS = {"GLTF": {"GLTF", "glTF"}}


def check_format_name_casing(readme_text: str, canonical_casing: dict[str, str] | None = None) -> list[dict]:
    """Hard gate (2026-08-08, Rule 1). A bare (non-extension) format-name word must use one
    consistent casing throughout the file, and where the format is a known entry in
    `canonical_casing` (sourced from `data/format_descriptions.json`'s keys, e.g.
    `{"XLSX": "XLSX", "PDF": "PDF", "HTML": "HTML"}`), that casing must match the registry's
    canonical form.

    Scope, stated precisely: only bare, standalone format words in PROSE are checked -- a
    dotted file-extension reference (`.xlsx`, `.msg`) is a separate, legitimate, always-
    lowercase convention (the literal on-disk suffix) and is never compared against the
    bare form; a markdown link TARGET (the `(...)` half of `[text](target)`, e.g. the bare
    filename `(LICENSE)`) and inline-code spans (`` `Xlsx` ``) are stripped before scanning
    entirely, since those are filename/identifier references, not prose format-name claims
    -- a real false positive found via this function's own test suite: the link target
    `(LICENSE)` (all-caps, a filename) was being compared against prose "License" as if
    they were the same format-name claim. Candidate words are further limited to those that
    are either a known registry format OR appear genuinely all-caps at least once in the
    remaining prose (a strong signal of being treated as an acronym/format name, not
    ordinary text) -- this is load-bearing, not decorative: an unrestricted bare-word scan
    would flag ordinary sentence-initial capitalization ("The" vs. "the") as a false
    "casing inconsistency" on every common English word.

    Returns a list of {"format", "found"/"found_variants", "canonical"?, "reason"}
    findings.
    """
    canonical_casing = canonical_casing or {}
    # Strip every `](target)` occurrence, not just the outermost one via _MD_LINK_RE's
    # capture groups -- a real residual leak found via two independent sub-agents' own
    # investigation of a badge-link false positive on pdf/*/html/python: for a nested badge
    # `[![CI](inner-href)](outer-href)`, replacing the whole match with `[{group(1)}]`
    # (the earlier fix) correctly drops the OUTER href but leaves the INNER image's own
    # href sitting untouched inside what becomes the "anchor text" placeholder -- e.g.
    # `[![CI](https://github.com/aspose-pdf-foss/...)]`, still containing "pdf" in a URL
    # path. `](...)` is unambiguous markdown link/image target syntax at ANY nesting depth
    # (real prose never contains a literal "](" sequence), so a single global sweep
    # removing every occurrence -- not just the outermost -- correctly clears both the
    # inner and outer href in one pass, with no recursion needed.
    prose_only = re.sub(r"\]\([^()\s]+\)", "]", readme_text)
    prose_only = re.sub(r"`[^`]*`", "", prose_only)
    occurrences: dict[str, set[str]] = {}
    all_caps_seen: set[str] = set()
    for match in _BARE_WORD_RE.finditer(prose_only):
        word = match.group(1)
        key = word.upper()
        if key in _GENERIC_ACRONYM_STOPLIST and key not in canonical_casing:
            continue
        occurrences.setdefault(key, set()).add(word)
        if word.isupper() and len(word) >= 2:
            all_caps_seen.add(key)

    findings: list[dict] = []
    for key in sorted(set(canonical_casing) | all_caps_seen):
        variants = occurrences.get(key, set())
        if not variants:
            continue
        if key in canonical_casing:
            correct = canonical_casing[key]
            for variant in sorted(variants):
                if variant != correct:
                    findings.append({
                        "format": key, "found": variant, "canonical": correct,
                        "reason": "bare format-name casing does not match the canonical registry form",
                    })
        elif len(variants) > 1:
            if variants <= _KNOWN_HEADING_CASE_EXCEPTIONS.get(key, set()):
                continue
            findings.append({
                "format": key, "found_variants": sorted(variants),
                "reason": "multiple different casings of the same bare format word used within this file",
            })
    return findings


_OWN_PRODUCT_LINE_RE = re.compile(r"^\[!\[|^#\s+", re.MULTILINE)


def check_no_cross_product_citation(
    readme_text: str, own_family: str, known_family_display_names: "set[str] | None" = None
) -> list[dict]:
    """Hard gate (2026-08-08). Flags a mention of a DIFFERENT product family's own name,
    package, or link inside a README that's supposed to describe only its own product --
    e.g. `pdf/cpp`'s Installation section citing `Aspose.Cells FOSS for C++`'s real NuGet
    package as "proof C++ can publish to NuGet." Found live, real, in exactly 3 files
    (`pdf/cpp`, `email/cpp`, `slides/cpp`, all citing `cells/cpp`) during the 2026-08-08
    Mermaid-simplification review -- the user's own verdict: a sibling product's own
    package name and link has no place inside a different product's own installation
    instructions, regardless of well-intentioned original reasoning ("proof the registry
    exists"). A visitor installing product A has no use for a citation about product B.

    `own_family` is this README's own product family slug (e.g. "pdf").
    `known_family_display_names` is the bounded set of real family names this repo actually
    tracks (sourced from `data/families.json`'s values, e.g. `{"Words", "PDF", "Cells", ...,
    "3D", ...}`, stripped of their "Aspose." prefix) -- **load-bearing, not optional in
    practice**: a real false-positive found via this function's own portfolio-wide test run
    confirms an unrestricted `Aspose\\.\\w+` scan matches far more than sibling PRODUCTS --
    `3d/net`'s own C# namespace `Aspose.ThreeD` (the digit-safe spelling of its own family,
    since C# identifiers can't start with "3" -- `data/families.json` itself only ever
    spells this family "Aspose.3D", so "ThreeD" isn't a registered family name at all and is
    correctly excluded once matching is restricted to the known set) and `words/net`'s
    internal tooling names (`Aspose.EnumExtensionsGenerator`, `Aspose.Foundation` -- neither
    a product family) were both being flagged as if citing a sibling product. Passing `None`
    here reverts to the old unrestricted-match behavior and will reproduce that noise --
    callers should always pass the real registry.

    Returns a list of {"family", "context"} findings for every mention of a different,
    KNOWN family's own `Aspose.{Family}` product name found outside a "Documentation &
    Resources"-style cross-reference section (matched case-insensitively, so this stays
    correct whether or not that heading has been title-cased yet -- the one legitimate
    place a sibling product might reasonably be mentioned, e.g. a "see also" pointer --
    never inside Installation/Quick start/API reference, which are strictly about THIS
    product).
    """
    findings: list[dict] = []
    exempt_section = re.search(
        r"^##\s+Documentation\s*&\s*[Rr]esources\s*$(.*?)(?=^##\s|\Z)", readme_text,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    exempt_span = exempt_section.span(1) if exempt_section else (-1, -1)
    known = {name.lower() for name in (known_family_display_names or set())}

    for match in re.finditer(r"\bAspose\.([A-Z][A-Za-z]*)\b", readme_text):
        cited_family = match.group(1)
        if cited_family.lower() == own_family.lower():
            continue
        if known_family_display_names is not None and cited_family.lower() not in known:
            continue
        if exempt_span[0] <= match.start() < exempt_span[1]:
            continue
        start = max(0, match.start() - 40)
        end = min(len(readme_text), match.end() + 40)
        findings.append({
            "family": cited_family,
            "context": readme_text[start:end].replace("\n", " "),
        })
    return findings


# 2026-08-08: IGNORECASE is load-bearing, not decorative -- a real regression found via a
# sub-agent's own investigation while title-casing headings portfolio-wide: this pattern
# was hardcoded to match only lowercase "## Additional examples". Once Rule 6 (title-case
# headings) landed and every file's heading became "## Additional Examples", the match
# would silently fail everywhere, making this hard gate permanently inert -- not just for
# the files this sprint touched, but for every future run, since no file will ever again
# have the old lowercase heading text. Same fix applied to the two sibling section-heading
# regexes below (API reference, Key capabilities) that had the identical defect.
_EXAMPLES_SECTION_RE = re.compile(
    r"^##\s+Additional examples\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE
)
_EXAMPLES_TABLE_RE = re.compile(r"^\|.+\|\s*$", re.MULTILINE)
_DETAILS_BLOCK_RE = re.compile(r"<details>.*?</details>", re.DOTALL)


def check_examples_table_collapsed(readme_text: str) -> list[dict]:
    """Hard gate (2026-08-08). The `## Additional examples` section's exhaustive per-item
    table (the "12 runnable examples" style `| Example | Shows |` table found live in
    `pdf/cpp` and several other products) must live INSIDE the same `<details>` block that
    already collapses the remaining worked-example prose walkthroughs -- not above it,
    always visible. The existing flagship-example rule already shows one example directly
    and collapses the rest; this closes the gap where the SUMMARY TABLE was exempted from
    that same treatment, working against the "simple at a glance" philosophy just applied
    to the diagram.

    Returns a list of {"reason": ...} findings; empty if the section has no such table, or
    the table is genuinely inside a `<details>` block.
    """
    section_match = _EXAMPLES_SECTION_RE.search(readme_text)
    if not section_match:
        return []
    section_text = section_match.group(1)

    table_match = _EXAMPLES_TABLE_RE.search(section_text)
    if not table_match:
        return []

    for details_match in _DETAILS_BLOCK_RE.finditer(section_text):
        if details_match.start() <= table_match.start() < details_match.end():
            return []

    return [{
        "reason": "the Additional examples table is not inside a <details> block -- it "
                  "must be collapsed alongside the remaining worked-example walkthroughs, "
                  "not always visible above the fold",
    }]


_TITLE_CASE_MINOR_WORDS = {
    "a", "an", "the", "and", "or", "but", "nor", "for", "so", "yet",
    "at", "by", "in", "of", "on", "to", "up", "as", "vs", "vs.", "via",
}


def _is_title_case(heading_text: str) -> bool:
    """A heading is title case when every "major" word starts with an uppercase letter.
    Minor words (articles, short prepositions/conjunctions) may stay lowercase except as
    the first word. A word that's already all-caps (an acronym like "API", "PDF") or
    contains internal capitals (a code identifier in backticks, "DocumentBuilder") always
    counts as correctly cased -- this check is about capitalization pattern, not spelling.
    """
    words = re.findall(r"[A-Za-z][A-Za-z0-9'.]*", heading_text)
    if not words:
        return True
    for index, word in enumerate(words):
        if word[0].islower() and word.lower() not in _TITLE_CASE_MINOR_WORDS:
            return False
        if index == 0 and word[0].islower():
            return False
    return True


def check_heading_title_case(readme_text: str) -> list[dict]:
    """Hard gate (2026-08-08, Rule 6). Every `##`/`###` heading and every `<summary>...
    </summary>` collapsible-heading text must be title case. Confirmed live: a 6-file
    sample found every heading in every file was sentence case ("At a glance", "Key
    capabilities", "View additional examples") -- a systemic pattern across the whole
    portfolio, not a one-off. Returns a list of {"heading", "kind"} findings for every
    non-title-case heading found; empty if all headings are already title case.
    """
    findings: list[dict] = []
    for match in _HEADING_RE.finditer(readme_text):
        text = match.group(2)
        if not _is_title_case(text):
            findings.append({"heading": text, "kind": "section"})
    for match in re.finditer(r"<summary>(.*?)</summary>", readme_text, re.DOTALL):
        text = match.group(1).strip()
        if not _is_title_case(text):
            findings.append({"heading": text, "kind": "summary"})
    return findings


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def check_section_job_distinctness(readme_text: str) -> list[dict]:
    """Heuristic (2026-08-08, Rule 5). Flags substantial sentence-level overlap between the
    intro paragraph (the README's implicit "why use this" content, before the first `##`
    heading) and the `## Key capabilities` section (the "features" content) -- a prompt for
    the mandatory judgment pass to merge or deduplicate, never an automatic fail, since
    genuine rhetorical restatement (a one-line hook echoing a capability) is often fine and
    "substantial overlap" is a content-quality judgment call a script can't fully automate.

    Overlap is measured per intro-sentence as word-set Jaccard similarity against each
    Key-capabilities bullet; a sentence sharing more than half its significant words
    (4+ letters, case-insensitive) with some bullet is flagged. Returns a list of
    {"intro_sentence", "overlapping_bullet", "similarity"} findings.
    """
    first_heading = re.search(r"^##\s", readme_text, re.MULTILINE)
    intro_text = readme_text[: first_heading.start()] if first_heading else readme_text

    caps_match = re.search(
        r"^##\s+Key capabilities\s*$(.*?)(?=^##\s|\Z)",
        readme_text, re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if not caps_match:
        return []
    bullets = re.findall(r"^-\s+(.+)$", caps_match.group(1), re.MULTILINE)
    if not bullets:
        return []

    def significant_words(text: str) -> set[str]:
        return {w.lower() for w in re.findall(r"[A-Za-z]{4,}", text)}

    findings: list[dict] = []
    for sentence in _SENTENCE_SPLIT_RE.split(intro_text.strip()):
        sentence_words = significant_words(sentence)
        if len(sentence_words) < 4:
            continue
        for bullet in bullets:
            bullet_words = significant_words(bullet)
            if not bullet_words:
                continue
            overlap = sentence_words & bullet_words
            similarity = len(overlap) / min(len(sentence_words), len(bullet_words))
            if similarity > 0.5:
                findings.append({
                    "intro_sentence": sentence.strip(),
                    "overlapping_bullet": bullet.strip(),
                    "similarity": round(similarity, 2),
                })
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check At-a-glance Mermaid diagram shape (2026-08-08 simplified model: "
                     "Product -> Core Capabilities -> Outputs, optional Starting Points)."
    )
    parser.add_argument("readme_path", help="Path to a readme.md file")
    parser.add_argument(
        "--pipeline-edges",
        default=None,
        help=(
            'JSON array of [from, to] capability-id pairs for this product, keyed to the '
            'CURRENT diagram\'s own node IDs, e.g. \'[["c1","c2"]]\'. Omit for products with '
            "no recorded entry in data/diagram_capability_dependencies.json (the check is a "
            "no-op then)."
        ),
    )
    args = parser.parse_args(argv)

    with open(args.readme_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    exit_code = 0

    unknown_ids = check_diagram_known_subgraph_ids(text)
    if unknown_ids:
        print(f"WARN: {args.readme_path} -- unrecognized subgraph ID(s): {', '.join(unknown_ids)}")

    column_findings = check_diagram_column_balance(text)
    if column_findings:
        exit_code = 1
        print(f"FAIL: {args.readme_path} -- column-balance violation(s):")
        for finding in column_findings:
            print(f"  {finding['reason']}")

    if args.pipeline_edges is not None:
        pipeline_edges = json.loads(args.pipeline_edges)
        dependency_findings = check_diagram_matches_capability_dependencies(text, pipeline_edges)
        if dependency_findings:
            exit_code = 1
            print(f"FAIL: {args.readme_path} -- {len(dependency_findings)} capability-dependency mismatch(es):")
            for finding in dependency_findings:
                print(f"  {finding['type']}: {finding['from']} -> {finding['to']}")
        else:
            print(f"PASS: {args.readme_path} -- diagram matches recorded capability dependencies")

    shape_findings = check_diagram_shape(text)
    if not shape_findings:
        print(f"PASS: {args.readme_path} -- diagram matches the Product -> Core Capabilities -> Outputs shape")
        return exit_code

    print(f"FAIL: {args.readme_path} -- {len(shape_findings)} diagram-shape violation(s):")
    for finding in shape_findings:
        print(f"  {finding['reason']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
