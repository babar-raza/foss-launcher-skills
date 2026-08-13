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
check_dropped_content() [hard gate at ingest-candidate -- a flagged link/heading needs an
explicit disposition in content-dispositions.json before the transition can pass; see the
content-unit checks below for prose-level coverage, which this link/heading-only check does
not itself provide], check_no_excluded_domain_links() [hard gate], check_named_member_accuracy()
[heuristic -- see its own docstring for an honest statement of what this heuristic
implementation can and cannot verify, versus the full per-language compiler-grade extraction the
plan's Verification pass section describes], check_api_reference_intro_names_classes()
[heuristic].

Old-README content-unit checks (Fifteenth incident / MT030, 2026-08-09 -- verify-and-merge of
real old-README prose beyond check_dropped_content's link/heading-only scope): extract_old_
readme_content_units() [pure extraction, not a check], check_content_unit_disposition_coverage()
[hard gate], check_content_unit_evidence_resolves() [hard gate], check_content_unit_merged_
into_target_section() [hard gate], check_content_unit_no_exact_duplicate_merge() [hard gate],
check_content_unit_classification_plausibility() [heuristic], check_content_unit_probable_
duplicate() [heuristic]. `dropped_claims.json`, referenced only as a docstring aspiration
throughout this module's history (2026-08-04 through 2026-08-09) and never actually
implemented by any code, is superseded by the real `content-dispositions.json` artifact these
checks read and write against -- see check_content_unit_disposition_coverage's own docstring.

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

from lib.api_table_dupes import find_duplicate_rows as _find_duplicate_rows
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
    "fragment", "fragments",
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
    "A3DW", "AMF", "DRACO", "USD", "CSS",
    # Added 2026-08-09, MT025 Phase 2 batches C/D -- confirmed real, currently-supported primary
    # formats for specific products, found missing from both this list and data/format_
    # descriptions.json during real content verification (font/python: TTF/OTF/CFF/Type1/EOT
    # font formats, each backed by a dedicated TtfFont/CffFont/Type1Font/EotFont class; note/
    # python: OneNote .one files, the product's sole input format).
    "TTF", "OTF", "CFF", "TYPE1", "EOT", "ONE", "ONENOTE",
})
_HYBRID_FROM_SCRATCH_LITERAL = "Nothing — authored from scratch"
# Tolerant of the ASCII "--" a composing agent (or a test fixture) may write in place of the
# real em dash "--" used in production content -- both are real, observed forms, not just a
# test-vs-prod inconsistency to paper over.
_HYBRID_FROM_SCRATCH_RE = re.compile(r"^Nothing\s*(?:--|—)\s*authored from scratch$")
_PURITY_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*")
_VERSION_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)*$")
_ARCHETYPES_REQUIRING_STARTING_POINTS = frozenset({"transform", "compile"})

# Twelfth incident / MT025 Phase 0c (2026-08-09): format-verification constants. See
# check_diagram_verified_format_claims's docstring for the full design rationale.
_FORMATS_TABLE_ROW_RE = re.compile(
    r"^\|\s*([A-Za-z0-9_.+-]+)[^|]*\|\s*(Yes|-)\s*\|\s*(Yes|-)\s*\|", re.MULTILINE
)
# The [^|]* after the format token (added 2026-08-09, MT025 Phase 2, found live in batch C):
# some products' formats.md cells carry trailing descriptive text in the Format column itself,
# e.g. "| CFB (Compound File Binary) | Yes | Yes |" (email/cpp, email/python) or "| MIME |"
# style variants (email/net) -- the original regex required the token to be immediately
# followed by the column-closing "|", so these rows silently matched nothing at all, making
# formats.md's directional-flag signal permanently absent for every email product regardless
# of its real content. Only the leading token is captured as the format name.
# Seed suffix lists, not claimed complete -- derived from real class/file names confirmed in 5
# products across C#/C++/Python (ObjLoadOptions/ObjSaveOptions, PdfWriter/DviWriter/SvgWriter,
# PdfConverter/PdfFileEditor). Expect real additions once Phase 2 rollout reaches Go/Rust/Java/
# TypeScript naming conventions not yet sampled.
_EXPORT_SUFFIXES = ("WRITER", "SAVEOPTIONS", "EXPORTER", "ENCODER", "SAVER")
_IMPORT_SUFFIXES = ("READER", "LOADOPTIONS", "IMPORTER", "DECODER", "LOADER")
# Found live during MT025 Phase 2's portfolio-wide rollup (2026-08-09): 3d/net's formats.md
# records the same real format under "MICROSOFT3MF" and 3d/typescript's under "THREEMF" (its
# real source classes are also spelled "ThreeMf" -- most languages can't start an identifier
# with a digit, forcing the word-spelled form) -- neither matches the "3MF" name every
# product's own prose and diagram actually use. An exact-match lookup/substring search silently
# treated real, Yes-flagged rows/classes as absent. A small, seed alias map, not claimed
# complete; extend as more extraction-vs-common-usage name mismatches are found this way.
_FORMAT_NAME_ALIASES = {"3MF": ("MICROSOFT3MF", "THREEMF")}


def _formats_table_lookup(formats_table: dict, canonical_format: str) -> dict:
    row = formats_table.get(canonical_format.upper())
    if row is not None:
        return row
    for alias in _FORMAT_NAME_ALIASES.get(canonical_format.upper(), ()):
        row = formats_table.get(alias)
        if row is not None:
            return row
    return {}
# Explicit "-only" phrasing only -- disclosed limitation, see check_diagram_verified_format_
# claims's docstring for why the 2-of-3 threshold is the real mitigation for what this misses.
_DIRECTION_ONLY_PHRASE_RE = re.compile(
    r"\b(import|export|read|write)[\s-]*only\b(?:\s+([A-Za-z][A-Za-z0-9]*))?", re.IGNORECASE
)
_NEGATION_WORD_NEGATES_DIRECTION = {
    "import": "export", "read": "export",
    "export": "import", "write": "import",
}


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


# check_diagram_format_support_claims (2026-08-08, Rule 2 refinement #1) was RETIRED 2026-08-09
# (Twelfth incident / MT025 Phase 0c), replaced by check_diagram_verified_format_claims (below).
# Direct code read confirmed the retired function was presence-only and direction-blind: its
# check `re.search(rf"\b{canonical}\b", formats_md_text, re.IGNORECASE)` matched the format NAME
# appearing ANYWHERE in the whole formats.md text -- never parsing the Import/Export COLUMN
# VALUE for that format's own row, and never checking the claim's direction (Starting Points =
# import, Outputs = export) against the correct column. A format whose real row read
# `Export: -` still passed as long as its name string appeared anywhere else in the file. This
# was a real, independent, pre-existing defect (not introduced by MT025) -- it simply never
# surfaced until formats.md's own unreliability was examined this closely. See
# check_diagram_verified_format_claims's docstring for the replacement design.


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

    Distinct from check_diagram_verified_format_claims (below, retired check_diagram_format_
    support_claims's successor): that function asks "if this node claims a format, is it
    genuinely, multiply-corroborated supported by this product" (accuracy); this function asks
    "is every node in this container a format claim AT ALL, and nothing else"
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
    union of `data/format_descriptions.json`'s keys (the same vocabulary `check_diagram_
    verified_format_claims`, below, uses) and `_DIAGRAM_SUPPLEMENTARY_FORMAT_NAMES` (below) --
    confirmed necessary by
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


def parse_formats_table(formats_md_text: str) -> dict[str, dict[str, bool]]:
    """Parse a `knowledge/{family}/{platform}/merged/formats.md`-style `| Format | Import |
    Export |` table into `{FORMAT: {"import": bool, "export": bool}}`. Shared by
    `check_diagram_format_completeness_hint` and `check_diagram_verified_format_claims` -- both
    used to inline this same regex separately; factored out 2026-08-09 (Twelfth incident /
    MT025 Phase 0c) so the table is parsed exactly one way, once. Returns `{}` for empty/absent
    input.
    """
    table: dict[str, dict[str, bool]] = {}
    for match in _FORMATS_TABLE_ROW_RE.finditer(formats_md_text or ""):
        fmt = match.group(1).upper()
        table[fmt] = {"import": match.group(2) == "Yes", "export": match.group(3) == "Yes"}
    return table


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
    done to any other check keyed off a source already known to have real staleness. (The
    directional VERIFICATION gate is `check_diagram_verified_format_claims`, below -- that one
    doesn't trust formats.md alone either, which is exactly why it's safe as a hard gate where
    this heuristic isn't.)

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
    for fmt, flags in parse_formats_table(formats_md_text).items():
        if archetype != "generative" and flags["import"] and fmt not in starting_text:
            findings.append({
                "format": fmt, "container": "starting_points",
                "reason": f"formats.md marks {fmt} Import=Yes but it is not named in the "
                          "Starting Points container",
            })
        if flags["export"] and fmt not in outputs_text:
            findings.append({
                "format": fmt, "container": "outputs",
                "reason": f"formats.md marks {fmt} Export=Yes but it is not named in the "
                          "Outputs container",
            })
    return findings


def _load_api_surface_names(api_surface_json_text: str) -> list[str]:
    """Extract every `name` and `file` field from a `knowledge/{family}/{platform}/merged/
    api_surface.json` array (2026-08-09, Twelfth incident / MT025 Phase 0c) -- real,
    structurally-extracted class/type names and source paths, confirmed reliable by direct read
    of 5 real portfolio files (uniform schema: an array of `{"name", "kind", "file", "methods",
    "properties", ...}` objects, produced by real source parsing, not prose). Returns `[]` for
    missing/empty/malformed input rather than raising -- this is a best-effort corroboration
    signal, not a required one; the 2-of-3 model in `check_diagram_verified_format_claims`
    tolerates its absence.
    """
    if not api_surface_json_text:
        return []
    try:
        entries = json.loads(api_surface_json_text)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(entries, list):
        return []
    names: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("name"):
            names.append(str(entry["name"]))
        if entry.get("file"):
            names.append(str(entry["file"]))
    return names


def _prose_direction_signal(prose_text: str, format_token: str, direction: str) -> bool:
    """Direction-aware prose corroboration (2026-08-09, Twelfth incident / MT025 Phase 0c).
    Searches `prose_text` (the candidate README with its Mermaid block already stripped by the
    caller -- passing raw markdown_text here would let a diagram corroborate itself) for
    `format_token` as a whole word. If found, checks the same sentence/line for an explicit
    `"import-only"` / `"export-only"` / `"read-only"` / `"write-only"` phrase that CONTRADICTS
    `direction`: a negative override (returns False even though the token is present), not just
    "not found". This is the specific mechanism that correctly discards `3d/net`'s real
    PLY-export contradiction (`"PLY is import-only"`) while still confirming its PLY-import
    claim from the same sentence.

    Disclosed limitation, not hidden: this only catches EXPLICIT "-only" phrasing -- a product
    stating the same fact differently (e.g. "cannot currently write COLLADA files") won't
    trigger the override. The 2-of-3 threshold in `check_diagram_verified_format_claims` is the
    real mitigation: a wrong prose signal alone can never flip the verdict by itself.

    Window boundary also stops at "; " (added 2026-08-09, MT025 Phase 2 portfolio-wide rollup):
    found live in 3d/net's real sentence "...COLLADA, and 3MF; PLY is import-only." -- with only
    ". "/newline as boundaries, the window for "3MF" incorrectly extended across the semicolon
    into PLY's own clause, so PLY's real "import-only" negation wrongly applied to 3MF's export
    claim too. A semicolon genuinely separates independent clauses in English (unlike a comma,
    which can sit inside one legitimate list -- "OBJ, STL, and 3MF" -- so commas are deliberately
    NOT added as boundaries here).

    Checks EVERY occurrence of `format_token`, not just the first (fixed the same day the
    semicolon boundary was added -- narrowing to a single clause per mention means a token
    genuinely mentioned in two different clauses, e.g. this exact PLY sentence: "...and PLY;
    PLY is import-only, unlike OBJ and STL." needs its SECOND mention's window checked too, or
    the negation in the second clause would never be seen from the first mention's own,
    correctly-narrower window). A negation found in ANY occurrence's window is decisive.
    """
    matches = list(re.finditer(rf"\b{re.escape(format_token)}\b", prose_text, re.IGNORECASE))
    if not matches:
        return False
    for match in matches:
        line_start = prose_text.rfind("\n", 0, match.start()) + 1
        sentence_start = max(
            prose_text.rfind(". ", line_start, match.start()),
            prose_text.rfind("; ", line_start, match.start()),
        )
        start = max(line_start, sentence_start + 2 if sentence_start != -1 else line_start)
        line_end = prose_text.find("\n", match.end())
        period_end = prose_text.find(". ", match.end())
        semicolon_end = prose_text.find("; ", match.end())
        ends = [e for e in (line_end, period_end, semicolon_end) if e != -1]
        end = min(ends) if ends else len(prose_text)
        window = prose_text[start:end]
        for neg_match in _DIRECTION_ONLY_PHRASE_RE.finditer(window):
            if _NEGATION_WORD_NEGATES_DIRECTION.get(neg_match.group(1).lower()) != direction:
                continue
            trailing = neg_match.group(2)
            # An ALL-CAPS trailing word (a cheap proxy for "looks like a format acronym", not
            # an ordinary continuation word like "here"/"mode"/"via") that differs from our own
            # token signals the negation is grammatically about THAT format, not ours -- e.g.
            # "Markdown (import-only XML via ...)": the negation is about XML, not Markdown,
            # even though both sit in the same clause-bounded window. Found live during MT025
            # Phase 2's portfolio-wide rollup (pdf/net). The ordinary "TOKEN is import-only"
            # pattern (no trailing word, or a lowercase continuation word) is unaffected.
            if trailing and trailing.isupper() and trailing.upper() != format_token.upper():
                continue
            return False
    return True


def _source_direction_signal(names: list[str], format_token: str, direction: str) -> bool:
    """Direction-aware source-evidence corroboration (2026-08-09, Twelfth incident / MT025
    Phase 0c). `names` is `api_surface.json`'s real class/file names (or a clone-cache filename
    list as a fallback when that JSON is thin/absent). A name containing `format_token` as a
    substring (case-insensitive; the token must be >= 3 characters to avoid short-token noise)
    with a matching directional suffix (`_EXPORT_SUFFIXES` for export, `_IMPORT_SUFFIXES` for
    import) counts specifically for that direction. A bare match with neither suffix (e.g.
    `PdfConverter`, `PdfFormat`) counts as weaker, generic evidence for BOTH directions -- real,
    structurally-extracted evidence the product genuinely has format-related code, just not
    which direction. A name matching only the OPPOSITE direction's suffix does not count as
    generic evidence for this direction (e.g. `PdfLoadOptions` corroborates import, not export).

    Also tries `_FORMAT_NAME_ALIASES` (added 2026-08-09, MT025 Phase 2 rollup): 3d/typescript's
    real "3MF" support is implemented as `ThreeMf`-named classes (most languages can't start an
    identifier with a digit) -- a literal "3MF" substring search would never find it.
    """
    candidate_tokens = [format_token, *_FORMAT_NAME_ALIASES.get(format_token.upper(), ())]
    candidate_tokens = [t for t in candidate_tokens if len(t) >= 3]
    if not candidate_tokens:
        return False
    suffixes = _EXPORT_SUFFIXES if direction == "export" else _IMPORT_SUFFIXES
    opposite_suffixes = _IMPORT_SUFFIXES if direction == "export" else _EXPORT_SUFFIXES
    for name in names:
        name_upper = name.upper()
        if not any(token.upper() in name_upper for token in candidate_tokens):
            continue
        if any(suffix in name_upper for suffix in suffixes):
            return True
        if not any(suffix in name_upper for suffix in opposite_suffixes):
            return True
    return False


def check_diagram_verified_format_claims(
    markdown_text: str,
    formats_md_text: str,
    api_surface_json_text: str | None = None,
    known_format_names: set[str] | None = None,
) -> list[dict]:
    """Hard gate (2026-08-09, Twelfth incident / MT025 Phase 0c). REPLACES the retired
    `check_diagram_format_support_claims`, which only checked whether a format NAME appeared
    ANYWHERE in formats.md's raw text -- never the Import/Export COLUMN VALUE for that format's
    own row, and never the claim's DIRECTION (Starting Points = import, Outputs = export)
    against the correct column. Confirmed by direct code read to be a real, independent,
    pre-existing defect, not something MT025 introduced.

    A format claim is VERIFIED (kept) only if at least 2 of these 3 independent signals agree
    for its specific direction; otherwise it is DISCARDED -- a hard-gate finding, never silently
    dropped and never silently trusted on formats.md's word alone:
      1. `formats.md`'s own directional flag (`parse_formats_table`).
      2. The candidate's own prose (README minus the Mermaid block), direction-aware via an
         explicit "-only" negation override (`_prose_direction_signal`).
      3. Real source evidence from `api_surface.json` / clone-cache filenames
         (`_source_direction_signal`).

    This design exists because `formats.md` is real (traces to genuine AST/tree-sitter source
    parsing) but independently confirmed unreliable for multiple real products in this exact
    portfolio: stale directional flags (`tex/python`'s PDF/DVI/SVG rows say Export=No despite
    the product genuinely producing all three -- `PdfWriter`/`DviWriter`/`SvgWriter` are real,
    confirmed classes), missing rows for a product's own primary format (`pdf/cpp` has no PDF or
    PNG row at all; `html/python` has no HTML row), spurious rows (`html/python`'s `BLOB`/
    `START`), and direct self-contradiction against the same file's own prose (`3d/net`'s
    formats.md claims PLY Export=Yes while the file's own intro and Key Capabilities both
    explicitly say "PLY is import-only"). `readme-refresh` cannot fix that upstream extractor
    from its own layer (a different skill's territory -- repo-scout/knowledge-enrich), so this
    must be permanently robust to formats.md being wrong in either direction, not contingent on
    someone else fixing it.

    Deliberately scoped to Starting Points (import) and Outputs (export) nodes only -- unlike
    the retired function, this does not check Capabilities nodes, where a format mention's
    direction is often genuinely ambiguous ("Multi-format load and save (OBJ, STL, ...)") and
    over-constraining risks false positives on legitimate descriptive prose.

    Returns a list of {"format", "direction", "node_id", "label", "signals", "reason"} findings
    for every claim scoring below 2 of 3 -- "signals" names exactly which of the 3 were
    true/false, so a finding tells a reviewer precisely what evidence is missing, not just that
    something failed.
    """
    known_format_names = known_format_names or set()
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []
    graph = parse_diagram(mermaid_text)
    formats_table = parse_formats_table(formats_md_text)
    api_surface_names = _load_api_surface_names(api_surface_json_text or "")
    prose_text = _MERMAID_BLOCK_FULL_RE.sub("", markdown_text)

    findings = []
    for node_id, kind in graph.node_subgraph.items():
        if kind not in ("starting_points", "outputs"):
            continue
        direction = "import" if kind == "starting_points" else "export"
        label = graph.node_label.get(node_id, "")
        core = label.split("(", 1)[0]
        # Found live during MT025 Phase 2 batch A (2026-08-09): a leading-letter-only token
        # regex silently exempted digit-leading format names (e.g. "3MF") from verification
        # entirely -- neither confirmed nor rejected, just invisible to this function, unlike
        # every letter-first format name. Confirmed by direct before/after interpolation test
        # on a real product. Broadened to allow a leading digit; safe, since a token still only
        # matters if it case-insensitively equals a real known_format_names entry.
        tokens = set(re.findall(r"[A-Za-z0-9][A-Za-z0-9+]{1,9}", core))
        for token in tokens:
            canonical = next(
                (f for f in known_format_names if f.upper() == token.upper()), None
            )
            if canonical is None:
                continue
            row = _formats_table_lookup(formats_table, canonical)
            sig_formats_md = bool(row.get(direction, False))
            sig_prose = _prose_direction_signal(prose_text, canonical, direction)
            sig_source = _source_direction_signal(api_surface_names, canonical, direction)
            score = sum((sig_formats_md, sig_prose, sig_source))
            if score < 2:
                findings.append({
                    "format": canonical, "direction": direction,
                    "node_id": node_id, "label": label,
                    "signals": {
                        "formats_md": sig_formats_md, "prose": sig_prose, "source": sig_source,
                    },
                    "reason": f"'{canonical}' ({direction}) claimed in {node_id} but only "
                              f"{score} of 3 corroborating signals are true (need >= 2) -- "
                              "discard or strengthen evidence before this claim can stay",
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


def check_enterprise_edition_link_resolves(
    readme_text: str, enterprise_link: "dict | None"
) -> list[dict]:
    """Hard gate (TC-HARDEN-19, MT034/Twentieth incident, 2026-08-12). `check_enterprise_
    edition_naming` (above) verifies a `products.aspose.com` link's anchor TEXT and surrounding
    CONTEXT -- it has never checked the link's TARGET (Gate Contract rule 6). A real clean-room
    regeneration pilot confirmed this is a live gap, not theoretical: `3d/typescript`'s
    regenerated candidate linked to `https://products.aspose.com/3d/typescript/`, a real,
    curl-confirmed 404 (the existing candidate's `https://products.aspose.com/3d/` returns 200);
    `barcode/python`'s regenerated link 301-redirected to a *different* enterprise bridge
    product (`/barcode/python-java/`) than the existing, correct one (`/barcode/python-net/`).

    `enterprise_link` is the factpack's own pre-verified `{"url", "type", "fallback_reason",
    "target_map_age_days", "target_map_stale"}` (from `_detect_enterprise_link`, run.py) --
    every real `products.aspose.com` href in the candidate must exactly match `enterprise_link
    ["url"]` (trailing-slash- and case-normalized). Two finding shapes:

    - `"no_verified_target"`: the candidate links to `products.aspose.com` but no verified
      target resolves for this product at all (`enterprise_link["url"]` is `None`, a genuine
      `BLOCKED_TARGET` from `backlink_targets.resolve_backlink`) -- the link must be removed
      entirely, never guessed, matching this skill's "never invent a specific version/command
      not backed by verified data" rule extended to links.
    - `"target_mismatch"`: the candidate's href does not match the one real, live-resolved
      target -- the composing agent guessed a slug instead of using the factpack's own verified
      value.

    Deliberately does not hard-fail on `enterprise_link["target_map_stale"]` alone (Evidence
    Contract rule 7) -- a stale cached target map is reduced-confidence evidence, not itself
    proof the link is wrong; staleness is surfaced in the factpack for the composing agent/
    reviewer to weigh, not used to block an otherwise-correct, still-cached-verified link.
    """
    findings: list[dict] = []
    verified_url = (enterprise_link or {}).get("url")
    normalized_verified = verified_url.rstrip("/").lower() if verified_url else None
    for match in _MD_LINK_RE.finditer(readme_text):
        anchor_text, href = match.group(1), match.group(2)
        if not _ENTERPRISE_LINK_HOST_RE.search(href):
            continue
        normalized_href = href.rstrip("/").lower()
        if normalized_verified is None:
            findings.append({
                "anchor_text": anchor_text, "href": href, "reason": "no_verified_target",
                "detail": "this candidate links to products.aspose.com, but no verified "
                          "Enterprise target resolves for this product in "
                          "data/aspose_com_targets.json -- remove the link, never guess a slug",
            })
            continue
        if normalized_href != normalized_verified:
            findings.append({
                "anchor_text": anchor_text, "href": href, "reason": "target_mismatch",
                "detail": f"this href does not match the one verified, live-resolving "
                          f"Enterprise target {verified_url!r} for this product",
                "verified_url": verified_url,
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


_BADGE_ROW_MARKER = "[!["
_BANNER_LINE_RE = re.compile(
    r"^!\[([^\]]*)\]\((https://products\.aspose\.org/media/"
    r"([A-Za-z0-9]+)/([A-Za-z0-9]+)/banner-readme\.png)\)\s*$"
)
# TC-HARDEN-27 (MT034, Twenty-First incident, 2026-08-12): a click-through-wrapped banner
# (`[![alt](banner_url)](homepage_url)`) -- distinct from the bare, unlinked form above.
_LINKED_BANNER_LINE_RE = re.compile(
    r"^\[!\[([^\]]*)\]\((https://products\.aspose\.org/media/"
    r"([A-Za-z0-9]+)/([A-Za-z0-9]+)/banner-readme\.png)\)\]\(([^)\s]+)\)\s*$"
)


def _find_banner_line(readme_text: str) -> "tuple[int, str] | tuple[None, None]":
    """Shared banner-line locator for check_banner_present/check_banner_links_to_homepage --
    the first non-blank line after the badge row (the first line containing `[![`)."""
    lines = readme_text.splitlines()
    badge_idx = next((i for i, line in enumerate(lines) if _BADGE_ROW_MARKER in line), None)
    if badge_idx is None:
        return None, None
    i = badge_idx + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return None, None
    return i, lines[i].strip()


def check_banner_present(readme_text: str, family: str, platform: str) -> list[dict]:
    """Hard gate (2026-08-09, MT026). Every candidate README must carry the real, live
    per-product banner asset (`https://products.aspose.org/media/{family}/{platform}/
    banner-readme.png` -- confirmed live for all 30 current products via direct HTTP check
    before this rule was written, not assumed) as an image line immediately after the badge
    row (the first line containing `[![`), with non-empty alt text -- either bare, or (TC-
    HARDEN-27, 2026-08-12) wrapped in a click-through link to the product's real homepage
    (check_banner_links_to_homepage, below, verifies which form is correct and, when linked,
    that the href itself is real).

    Also requires the URL's own embedded family/platform segments to match the product actually
    being checked -- not defensive programming for its own sake: this exact session already
    found real cross-product content contamination twice (a snapshot-contamination incident
    during an earlier parallel-agent rollout, and a sibling-product citation bug in an
    Installation section) -- a banner is exactly the kind of easy-to-copy-paste-wrong element
    that failure class would produce silently, and this check makes it structurally impossible
    to ship undetected.

    Returns a list of {"reason": ...} findings, empty if the banner is present, correctly
    placed, and correctly matches this product.
    """
    idx, line = _find_banner_line(readme_text)
    if idx is None:
        lines = readme_text.splitlines()
        if not any(_BADGE_ROW_MARKER in l for l in lines):
            return [{"reason": "no badge row found to anchor banner placement"}]
        return [{"reason": "no banner line found after the badge row"}]

    match = _BANNER_LINE_RE.match(line)
    if match:
        alt_text, url, url_family, url_platform = match.groups()
    else:
        linked_match = _LINKED_BANNER_LINE_RE.match(line)
        if not linked_match:
            return [{
                "reason": "expected a banner image line "
                          "(![alt](https://products.aspose.org/media/{family}/{platform}/"
                          "banner-readme.png)), optionally wrapped in a homepage link "
                          f"([![...](...)]([homepage])), immediately after the badge row, "
                          f"found: {line!r}",
            }]
        alt_text, url, url_family, url_platform, _homepage_href = linked_match.groups()

    findings = []
    if not alt_text.strip():
        findings.append({"reason": "banner image has empty alt text"})
    if url_family.lower() != family.lower() or url_platform.lower() != platform.lower():
        findings.append({
            "reason": f"banner URL family/platform ({url_family}/{url_platform}) does not "
                      f"match this product ({family}/{platform}) -- likely cross-product "
                      "contamination",
        })
    return findings


def check_banner_links_to_homepage(readme_text: str, homepage: "dict | None") -> list[dict]:
    """Hard gate (TC-HARDEN-27, MT034/Twenty-First incident, 2026-08-12). New requirement,
    distinct from MT026's own "keep the banner unlinked" decision (2026-08-09) -- that decision
    solved a different, already-settled problem (the banner IMAGE's own URL being confused with
    a real, 5-minute-expiring signed GitHub social-preview URL). This wraps the same, still-
    stable, already-live-verified banner image in a click-through link to the product's real
    `products.aspose.org/{family}/{platform}/` homepage, with an explicit "must never be broken"
    reliability bar.

    `homepage` is the factpack's `{"url", "verified"}` (from `_detect_homepage_link`, run.py) --
    `verified` is True only when `content/products.aspose.org/en/{family}/{platform}/_index.md`
    genuinely exists in this repo: a first-party, same-repo-deploy guarantee, structurally
    stronger than the Enterprise-link's cached-external-site case (Evidence Contract rule 7)
    since this site is built and deployed directly from this repo's own `content/` tree.

    - `homepage["verified"]` True: the banner line MUST be the linked form
      (`[![alt](banner_url)](homepage_url)`), and the href must exactly match `homepage["url"]`
      (trailing-slash- and case-normalized) -- never a guessed/invented URL.
    - Not verified (no confirmed local page exists): the banner MUST stay the plain, unlinked
      form -- linking to an unconfirmed page is exactly the invented-URL class this module's
      other checks (e.g. Documentation & Resources links) already forbid.

    A malformed banner line, or no banner line at all, is check_banner_present's own finding --
    this function returns [] rather than duplicate it.
    """
    idx, line = _find_banner_line(readme_text)
    if idx is None:
        return []

    linked_match = _LINKED_BANNER_LINE_RE.match(line)
    unlinked_match = None if linked_match else _BANNER_LINE_RE.match(line)
    if not linked_match and not unlinked_match:
        return []

    verified_url = (homepage or {}).get("url")
    is_verified = bool((homepage or {}).get("verified") and verified_url)

    if linked_match:
        href = linked_match.group(5)
        if not is_verified:
            return [{
                "reason": "banner links to a homepage page with no verified local "
                          "content/products.aspose.org/en/{family}/{platform}/_index.md -- "
                          "remove the link rather than pointing at an unconfirmed page",
                "href": href,
            }]
        if href.rstrip("/").lower() != verified_url.rstrip("/").lower():
            return [{
                "reason": "banner links to a homepage URL that does not match the one "
                          "verified, real homepage for this product",
                "href": href,
                "verified_url": verified_url,
            }]
        return []

    if is_verified:
        return [{
            "reason": "a real, verified homepage page exists for this product but the banner "
                      "is not linked to it",
            "verified_url": verified_url,
        }]
    return []


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

    TC-HARDEN-25 (MT034 reproof, 2026-08-12): a License section may legitimately contain more
    than one link -- found live during a real clean-room regeneration, where a legitimate
    cross-reference to the sibling `upstream-issues.md` sat in the same section as the real
    license link and, taken positionally as "the first link," misfired this gate on a
    perfectly correct candidate. Prefer the link whose anchor text actually names the license
    (matching the Template section's own fixed `[MIT License](...)` wording) over raw position;
    fall back to the first link only when none qualifies, so every existing single-link section
    (the common case across the whole portfolio) is unaffected.
    """
    license_match = re.search(r"^##\s+License\s*$(.*?)(?=^##\s|\Z)", readme_text, re.MULTILINE | re.DOTALL)
    if not license_match:
        return []
    section_text = license_match.group(1)
    links = list(_MD_LINK_RE.finditer(section_text))
    if not links:
        return []
    link_match = next((m for m in links if "license" in m.group(1).lower()), links[0])
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


_LICENSE_TEMPLATE_LINKED_FMT = (
    "This project is licensed under the [MIT License]({path}). The MIT License permits use, "
    "copying, modification, distribution, sublicensing, and commercial use, provided its "
    "copyright and permission notice are retained. The software is provided without warranty."
)
_LICENSE_TEMPLATE_UNLINKED = (
    "This project is licensed under the MIT License. The MIT License permits use, copying, "
    "modification, distribution, sublicensing, and commercial use, provided its copyright and "
    "permission notice are retained. The software is provided without warranty."
)


def _normalize_prose_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def check_license_section_matches_template(
    readme_text: str, license_file: "dict | None"
) -> list[dict]:
    """Hard gate (TC-HARDEN-26, MT034/Twenty-First incident, 2026-08-12). The 2026-08-04
    License-template rule (Template section: "fixed template, no free-form prose", baked in
    after `3d/typescript`'s original free-form-narration incident) was never actually turned
    into a mechanical gate -- the only check this plan ever spec'd for it,
    check_license_link_target (above), was scoped to the section's LINK TARGET only, never its
    PROSE (confirmed by direct grep of this module before this function existed: zero functions
    checked License-section text content). A completely blind clean-room regeneration of the
    same product (`3d/typescript`, this session's own MT034 reproof) independently reproduced
    the identical defect class with different wording -- proof the rule was written into this
    plan's prose but never enforced by its code, the same "plan names the right rule, skill code
    never enforces it" shape as Anti-Overclaim rule 8, recurring in this exact section a second
    time.

    Verifies the `## License` section's text (whitespace-normalized, so real line-wrap variance
    across products never matters) STARTS WITH the exact fixed template sentence -- linked form
    using `license_file["relative_path"]` when a real license file was detected, or the unlinked
    form when `license_file` is falsy. "Starts with", not "equals exactly", so real, already-
    established legitimate additional content (e.g. `pdf/go`'s real bundled third-party font
    disclosure, Template section 2026-08-04) may still follow the template without tripping this
    gate -- only a section that replaces the template with unrelated free-form prose, this
    incident's own shape, fails.
    """
    section_match = re.search(r"^##\s+License\s*$(.*?)(?=^##\s|\Z)", readme_text, re.MULTILINE | re.DOTALL)
    if not section_match:
        return []
    section_text = _normalize_prose_whitespace(section_match.group(1))
    relative_path = (license_file or {}).get("relative_path")
    if relative_path:
        expected = _normalize_prose_whitespace(_LICENSE_TEMPLATE_LINKED_FMT.format(path=relative_path))
    else:
        expected = _LICENSE_TEMPLATE_UNLINKED
    if section_text.startswith(expected):
        return []
    return [{
        "reason": "License section does not start with the fixed template sentence "
                  "(Template section, 2026-08-04) -- looks like free-form/narration prose "
                  "instead of the required fixed wording",
        "expected_start": expected,
        "actual_start": section_text[:len(expected) + 60],
    }]


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
    # TC-HARDEN-26 (MT034, Twenty-First incident, 2026-08-12): a fresh, blind clean-room
    # regeneration of 3d/typescript independently reproduced the identical License-section
    # narration-leak defect class the 2026-08-04 incident already found on this same product,
    # with new wording none of the phrases above matched -- a secondary safety net alongside
    # the new, primary check_license_section_matches_template hard gate.
    r"\bthe previous version of this readme\b",
    r"\bin this repository snapshot\b",
    r"\bif formally applied as declared\b",
    r"\btreat the license status as unconfirmed\b",
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


# Seeded, non-exhaustive -- confirmed live across the real portfolio at design time (2026-08-12):
# "has not been published yet" (most products), "No {Registry} package has been published for
# this library yet" (email/cpp, pdf/cpp -- negation via "No", not "not"), "is not yet published
# to a package registry" (slides/cpp). Expect real additions as more phrasing variants surface.
_UNPUBLISHED_PACKAGE_SIGNAL_RE = re.compile(
    r"has\s+not\s+(?:yet\s+)?been\s+published"
    r"|has\s+been\s+published\s+for\s+this\s+library\s+yet"
    r"|is\s+not\s+yet\s+published",
    re.IGNORECASE,
)


def check_installation_matches_package_registry(readme_text: str, install_info: dict) -> list[dict]:
    """Heuristic (2026-08-12, TC-HARDEN-32, MT035) -- NOT a hard gate; see below for why.
    No prior check anywhere verified the composed `## Installation` section against real
    package/install data -- `_detect_install_info`'s factpack signal (`published`/
    `fallback_text_required`) was computed but never read back against the section's actual
    composed text, a real portfolio-wide gap, maximally exposed for a genuinely new product
    (guaranteed to have no `data/package_registry.json` entry yet).

    Two directions, matching this plan's own established "never invent a URL/version/command
    not backed by verified data" rule:

    1. **Unpublished (`fallback_text_required: True`)**: the section should disclose this using
       one of the real, already-established portfolio conventions (see
       `_UNPUBLISHED_PACKAGE_SIGNAL_RE`) -- never a specific install command presented as if a
       real package exists.
    2. **Published (`fallback_text_required: False`)**: the section should name the real,
       confirmed package identity from `data/package_registry.json`'s own `candidate` field
       (case-insensitively -- see below) -- `artifact_id` for Maven (the identifier actually
       used in a real dependency declaration, not `group_id`), `module_path` for Go modules,
       `name` for every other registry type (PyPI/NuGet/npm/crates.io).

    **Why this is a heuristic, not a hard gate -- confirmed by direct, live evidence the moment
    this check was first run against real content, not a theoretical caveat**: `data/
    package_registry.json` was found to be independently wrong, in BOTH directions, for real
    products already in this portfolio. `words/net`'s entry reads `published: false`, but the
    real, live NuGet API (`api.nuget.org/v3-flatcontainer/aspose.words.foss/index.json`)
    confirms `Aspose.Words.FOSS` v26.2.0 genuinely IS published right now -- the registry's own
    `published` flag is stale relative to the real world (and relative to the README's own
    already-correct `dotnet add package Aspose.Words.FOSS` content, which is right). `email/
    net`'s `candidate.name` is `"Aspose.Email.FOSS"`, but the real, live nuspec
    (`aspose.email.foss.nuspec`) confirms the actual published package ID's real casing is
    `Aspose.Email.Foss` -- matching the README's own already-correct content, not the registry.
    This is the identical "even structured, real, checked-in data isn't infallible" lesson
    `formats.md` already taught this plan (MT025's Twelfth incident) -- a hard gate here would
    have blocked two ALREADY-CORRECT candidates over stale registry data, exactly the mistake
    that lesson exists to prevent. The package-identity comparison is also case-insensitive for
    the same reason (both confirmed real NuGet-casing mismatches were case-only) -- NuGet/PyPI/
    npm package IDs are conventionally case-insensitive anyway, so an exact-case match was never
    the right bar for "is this the right package," only a distraction from it.

    Degrades gracefully, never a finding on its own: no `## Installation` section
    (`check_required_sections` already owns that), no real registry data at all for this
    product, or incomplete `candidate` data (nothing to compare against) all return no findings.

    Returns `{"reason", "expected"?}` findings -- a prompt for human/agent judgment (matching
    this module's other data-source-dependent heuristics, e.g. `check_diagram_format_
    completeness_hint`), never an automatic fail.
    """
    sections = _split_into_sections(readme_text)
    section_text = sections.get("Installation", "")
    if not section_text:
        return []

    fallback_required = install_info.get("fallback_text_required")
    if fallback_required is None:
        return []

    if fallback_required:
        if not _UNPUBLISHED_PACKAGE_SIGNAL_RE.search(section_text):
            return [{
                "reason": "Installation section does not disclose that no confirmed published "
                          "package exists yet for this product (data/package_registry.json "
                          "shows fallback_text_required=True) -- confirm whether this is a real "
                          "gap or the registry data itself is stale before treating this as a "
                          "content defect",
            }]
        return []

    candidate = install_info.get("candidate") or {}
    registry_type = install_info.get("registry_type")
    if registry_type == "maven":
        expected = candidate.get("artifact_id")
    elif registry_type == "go_modules":
        expected = candidate.get("module_path")
    else:
        expected = candidate.get("name")
    if not expected:
        return []
    if expected.lower() not in section_text.lower():
        return [{
            "reason": f"Installation section does not name the real, confirmed published "
                      f"package identity '{expected}' (data/package_registry.json, "
                      f"registry_type={registry_type!r}) -- confirm whether this is a real gap "
                      f"or the registry data itself is stale before treating this as a content "
                      f"defect",
            "expected": expected,
        }]
    return []


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

# Same conservative, deliberately-small emoji range as the MT030 content-unit prefilter --
# real, commonly-used decorative heading emoji, not an exhaustive Unicode-emoji sweep.
_DROP_MATCH_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿️]")


def _normalize_for_drop_match(text: str) -> str:
    """Strip emoji, casefold, and collapse whitespace -- used by check_dropped_content's
    heading comparison so a legitimate rename (emoji stripped, title-cased per
    check_heading_title_case) doesn't read as a drop. See check_dropped_content's own
    docstring/inline comment for the real, confirmed incident this closes."""
    no_emoji = _DROP_MATCH_EMOJI_RE.sub("", text)
    return re.sub(r"\s+", " ", no_emoji).strip().casefold()


def check_dropped_content(old_readme_text: str, new_readme_text: str, clone_cache_root: str) -> dict:
    """Diff the old (upstream) README against the new candidate for links and H2/H3 headings
    present in the old file with no match anywhere in the new one. Hard gate at
    ingest-candidate, per the "Never drop original-README content without a verified reason"
    rule. Scoped to links/headings only -- see check_content_unit_disposition_coverage (Fifteenth
    incident / MT030) for the real prose-level coverage this function's own docstring aspired to
    (2026-08-04 through 2026-08-09) but never actually implemented via any `dropped_claims.json`
    mechanism; that real mechanism is `content-dispositions.json`, read/written by the checks
    below, not this one.

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

    # Real, confirmed bug (found live 2026-08-09, MT030 Phase 1, independently by 3 of 5 pilot
    # agents across words/net/pdf/cpp/note/python): a raw, literal substring match against the
    # OLD heading text -- emoji and original casing intact -- can NEVER succeed once
    # check_heading_title_case (a later rule, 2026-08-08) forces every new heading to be
    # emoji-free and title-cased. "✨ Features" -> "Key Capabilities" is a legitimate rename with
    # the underlying content fully preserved, but the literal string "✨ Features" can never
    # reappear anywhere in a compliant candidate -- this hard gate was silently, structurally
    # unsatisfiable for any old README using emoji'd/non-title-case headings (common in this
    # portfolio) until this fix. Both sides are normalized (emoji stripped, casefolded,
    # whitespace-collapsed) before the substring test; a genuinely dropped heading -- one whose
    # normalized text truly appears nowhere in the new candidate -- still correctly flags.
    old_headings = {m.group(2) for m in _HEADING_RE.finditer(old_readme_text)}
    normalized_new_text = _normalize_for_drop_match(new_readme_text)
    dropped_headings = sorted(
        h for h in old_headings if _normalize_for_drop_match(h) not in normalized_new_text
    )

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


def check_named_member_accuracy(
    readme_text: str, clone_cache_root: str, reference_dir: str | None = None
) -> list[dict]:
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

    `reference_dir` (added 2026-08-09, MT027): the directory `content/reference.aspose.org/en/
    {family}/{platform}/`, if given. When a partial-class page (`{reference_dir}/{ClassName}.md`)
    exists for a cited class, it becomes the PREFERRED evidence source for that class -- real,
    already-graded `## Properties`/`## Methods` tables (`parse_reference_class_page`) instead of
    a raw clone-cache grep, since a real signature/property table is stronger evidence than
    "this token appears somewhere in the file's text." The clone-cache-grep path stays the
    fallback for any class with no reference-site page, exactly matching MT025's own "primary
    signal, cheaper fallback" precedent for `api_surface.json` vs. clone-cache filename search.
    `None` (the default) preserves this function's exact prior behavior, unchanged.
    """
    root = Path(clone_cache_root)
    ref_dir = Path(reference_dir) if reference_dir else None
    if not root.is_dir() and not (ref_dir and ref_dir.is_dir()):
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
            known_members: set[str] = set()
            reference_page = ref_dir / f"{class_name}.md" if ref_dir else None
            if reference_page is not None and reference_page.is_file():
                parsed = parse_reference_class_page(
                    reference_page.read_text(encoding="utf-8", errors="ignore")
                )
                known_members = set(parsed["properties"]) | set(parsed["methods"])

            candidate_files = _find_class_source_files(root, class_name) if root.is_dir() else []
            combined_text = (
                "\n".join(f.read_text(encoding="utf-8", errors="ignore") for f in candidate_files)
                if candidate_files else ""
            )
            if not known_members and not candidate_files:
                continue  # no evidence either way -- not a fabrication claim, skip silently

            for member in members:
                member_token = member.split("(")[0].split(":")[0].strip()
                if not member_token:
                    continue
                if member_token in known_members:
                    continue
                if combined_text and member_token in combined_text:
                    # Confirmed real by clone-cache source even though it's missing from the
                    # reference-site page's own Properties/Methods tables -- found live during
                    # MT027's full-portfolio sanity pass (2026-08-09): reference.aspose.org's
                    # own extraction systematically missed several real getter methods (e.g.
                    # email/cpp's `subject()`/`body()`, present only as their `set_X` setter
                    # counterparts in that class's real, graded page) -- the same "even graded
                    # content can be incomplete" lesson already applied to the class-existence
                    # check, now applied at the member level too.
                    continue
                source_desc = (
                    f"{class_name}'s real reference.aspose.org Properties/Methods tables"
                    if known_members else f"{len(candidate_files)} candidate source file(s)"
                )
                if known_members and candidate_files:
                    source_desc = (
                        f"{class_name}'s real reference.aspose.org Properties/Methods tables "
                        f"nor {len(candidate_files)} candidate clone-cache source file(s)"
                    )
                findings.append({
                    "class_name": class_name,
                    "member": member,
                    "reason": f"not found in {source_desc}",
                })
    return findings


# TC-HARDEN-34 (MT035, 2026-08-12): the original 9 extensions exactly matched the 7 languages
# this portfolio used at the time (Python/Java/C#/Go/Rust/C++/TypeScript); PHP/Kotlin/Ruby/Swift
# added as confirmed-real, bounded additions -- see _find_class_source_files' own docstring.
_CLASS_SOURCE_EXTENSIONS = frozenset({
    ".py", ".java", ".cs", ".go", ".rs", ".cpp", ".hpp", ".h", ".ts", ".c",
    ".php", ".kt", ".kts", ".rb", ".swift",
})


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

    `enum`/`type` added to the keyword list (2026-08-09, MT027, found live in the full-portfolio
    sanity pass): 3d/typescript's real `ExtrapolationType`/`StepMode` are declared as `export
    enum ExtrapolationType { ... }` -- the original `class|struct|interface|def` list has no
    TypeScript/Rust/Go enum or type-alias keyword at all, so every enum-shaped citation in any
    product using this pattern was silently unconfirmable by this function regardless of how
    real it was.

    `_CLASS_SOURCE_EXTENSIONS` widened (2026-08-12, TC-HARDEN-34, MT035): the original 9-extension
    set exactly matched the 7 languages this portfolio happened to use at the time -- a genuinely
    new language's real source files were invisible to this function (and therefore to
    `check_named_member_accuracy` and `check_api_reference_classes_exist_in_reference_site`'s
    clone-cache fallback) even once a real clone cache existed, a *permanent* blind spot for that
    language, not one that resolves once `/repo-scout` runs. Widened to the 4 languages this
    taskcard's own audit named as confirmed-real candidates (PHP, Kotlin, Ruby, Swift -- each
    confirmed to use the literal `class`/`struct`/`interface`/`enum` keywords this function's own
    regex already recognizes, so no keyword-list change was needed, only the extension set) -- a
    deliberate, bounded widening (exactly these languages, not an open-ended "any extension"
    policy), per this taskcard's own explicit Forbidden-actions constraint against scanning
    generated/vendor/binary files and producing false corroboration signals.
    """
    declare_re = re.compile(
        rf"\b(?:class|struct|interface|def|enum|type)\s+{re.escape(class_name)}\b(?!\s*;)"
    )
    skip_dirs = {".git", "node_modules", "__pycache__", "target", "build", "dist", "bin", "obj"}
    found: list[Path] = []
    for path in root.rglob("*"):
        if len(found) >= max_files:
            break
        if not path.is_file() or path.suffix not in _CLASS_SOURCE_EXTENSIONS:
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


# check_api_reference_intro_names_classes (2026-08-05) was RETIRED 2026-08-09 (MT027) --
# absorbed into check_api_reference_classes_exist_in_reference_site (below), which runs the
# same two bad-pattern checks PLUS real class-name verification against reference.aspose.org,
# and was elevated from heuristic to hard gate now that class-name verification makes the
# underlying question mechanically decidable. See that function's docstring for the full
# rationale. _API_REF_SECTION_RE (the intro-only section extractor) is kept -- still used there.
_API_REF_SECTION_RE = re.compile(
    r"^##\s+API reference\s*$(.*?)(?=<details>|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE
)


# --- MT027 (2026-08-09): ground `## API Reference` in reference.aspose.org's own graded
# content. See check_api_reference_classes_exist_in_reference_site's docstring for the full
# design rationale.

_FRONTMATTER_BOUNDS_RE = re.compile(r"^---\s*$", re.MULTILINE)
_REF_INDEX_MODULE_HEADER_RE = re.compile(r"^##\s+(.+?)\s*$")
_REF_INDEX_TABLE_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(.*?)\s*\|\s*$")
_REF_CLASS_PROPERTY_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")
_REF_CLASS_METHOD_ROW_RE = re.compile(r"^\|\s*`([A-Za-z_][A-Za-z0-9_]*)\s*\(")

# Fallback convention (2026-08-11) -- confirmed real and unique to `3d/typescript`'s _index.md
# (a full 30-product scan found every other product's real modules already yield real classes via
# the table convention above; only this one has real modules with zero table rows). Instead of a
# `| Class | Description |` table, this file lists each class as its own `### ClassName` (or
# `### [ClassName](link)`) heading followed by a real prose paragraph. A heading may name several
# classes at once, comma-separated inside the heading/link text (confirmed real: one heading,
# "Material, LambertMaterial, PhongMaterial, PbrMaterial", covering 4 classes) -- each gets the
# same description (the heading's own first paragraph, stopped at the first blank line so a
# following bullet list or second paragraph isn't slurped whole into one table cell).
_REF_INDEX_CLASS_HEADING_RE = re.compile(r"^###\s+(?:\[([^\]]+)\]\([^)]*\)|(.+?))\s*$")


def _strip_frontmatter(text: str) -> str:
    """Strip a leading `---\\n...\\n---\\n` YAML frontmatter block, if present. Shared by both
    reference.aspose.org parsers below -- the `evidence`/`grade`/`provenance` fields inside it
    are internal-only (this repo's own established rule) and must never reach either parser's
    output, which ultimately feeds README prose.
    """
    matches = list(_FRONTMATTER_BOUNDS_RE.finditer(text))
    if len(matches) >= 2 and matches[0].start() == 0:
        return text[matches[1].end():]
    return text


def _parse_class_heading_module(lines: list[str]) -> list[dict]:
    """Fallback parser (2026-08-11) for a reference.aspose.org module block that lists its
    classes as individual `### ClassName` (or `### [ClassName](link)`) headings followed by a
    real prose paragraph, rather than a `| Class | Description |` table -- see
    `_REF_INDEX_CLASS_HEADING_RE`'s module comment for the confirmed-real, 3d/typescript-specific
    motivation. Only called for a module that yielded zero table rows; a module's own intro prose
    before its first `###` heading (confirmed real, e.g. "OBJ Format"'s "OBJ supports both import
    and export...") is correctly skipped since it precedes any heading match.
    """
    entries: list[dict] = []
    i, n = 0, len(lines)
    while i < n:
        heading_match = _REF_INDEX_CLASS_HEADING_RE.match(lines[i])
        if not heading_match:
            i += 1
            continue
        names_text = heading_match.group(1) or heading_match.group(2) or ""
        class_names = [name.strip() for name in names_text.split(",") if name.strip()]
        i += 1
        while i < n and not lines[i].strip():
            i += 1
        desc_lines: list[str] = []
        while i < n and lines[i].strip() and not lines[i].lstrip().startswith("#") \
                and lines[i].strip() != "---":
            desc_lines.append(lines[i].strip())
            i += 1
        description = " ".join(desc_lines).strip()
        for class_name in class_names:
            entries.append({"class": class_name, "description": description})
    return entries


def parse_reference_api_index(index_md_text: str) -> dict[str, list[dict]]:
    """Parse a `content/reference.aspose.org/en/{family}/{platform}/_index.md`'s real body
    into `{module_name: [{"class": ..., "description": ...}, ...]}`. Confirmed real structure
    from 5 direct file reads (2026-08-09): a flat `##`-module-grouped `| Class | Description |`
    table (module names vary per product -- `Core API`, `Annotations`, `Drawing`, `Facades`,
    `Forms` for `pdf/cpp`; `Core API`, `Presentation` for `tex/python`), with a `### Enumerations`
    sub-table nested inside some modules -- folded into the same parent module's list here (both
    are real, citable public types for the purposes of "does this class/enum name exist").

    Fallback (2026-08-11, closes a real MT028 gap): a module with zero table rows but real
    `### ClassName` headings uses the alternate class-heading-per-entry convention
    (`_parse_class_heading_module`) instead -- confirmed unique to `3d/typescript`'s _index.md by
    a full 30-product scan (every other product's real modules already yield classes via the
    table convention). MT028's original rollout found this file didn't match the table
    convention and excluded the product entirely as a "structural outlier" rather than parsing
    its real, equally-valid alternate convention -- this fallback closes that gap rather than
    leaving the product's real, well-organized class list unmirrored.

    Frontmatter (`evidence`/`grade`/`provenance` -- confirmed internal-only, matching this
    repo's established rule) is stripped before parsing and never appears in the result.

    Returns `{}` for empty input -- callers must treat that as "no reference-site data for this
    product," never as "this product genuinely has zero public types."
    """
    body = _strip_frontmatter(index_md_text or "")
    index: dict[str, list[dict]] = {}
    module_lines: dict[str, list[str]] = {}
    current_module: str | None = None
    for line in body.splitlines():
        header_match = _REF_INDEX_MODULE_HEADER_RE.match(line)
        if header_match:
            current_module = header_match.group(1).strip()
            index.setdefault(current_module, [])
            module_lines.setdefault(current_module, [])
            continue
        if current_module is None:
            continue
        module_lines[current_module].append(line)
        row_match = _REF_INDEX_TABLE_ROW_RE.match(line)
        if row_match:
            index[current_module].append({
                "class": row_match.group(1), "description": row_match.group(2),
            })
    for module, rows in index.items():
        if rows:
            continue
        block = module_lines.get(module, [])
        if any(_REF_INDEX_CLASS_HEADING_RE.match(candidate) for candidate in block):
            index[module] = _parse_class_heading_module(block)
    return index


def parse_reference_class_page(page_md_text: str) -> dict[str, list[str]]:
    """Parse a `content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md` partial-
    class page's real `## Properties`/`## Methods` tables into `{"properties": [name, ...],
    "methods": [name, ...]}` -- real, already-graded member names, confirmed from a direct read
    of `tex/python/TeXJob.md` (real signatures like `` `__init__(source: InputSource, ...)` ``,
    real property rows like `` `messages` | `list[str]` | Read | ... ``). Frontmatter stripped
    first, same as `parse_reference_api_index`. Returns `{"properties": [], "methods": []}` for
    empty/unparseable input.
    """
    body = _strip_frontmatter(page_md_text or "")
    result: dict[str, list[str]] = {"properties": [], "methods": []}
    section: str | None = None
    for line in body.splitlines():
        heading_match = re.match(r"^##\s+(.+?)\s*$", line)
        if heading_match:
            title = heading_match.group(1).strip().lower()
            section = title if title in ("properties", "methods") else None
            continue
        if section == "properties":
            prop_match = _REF_CLASS_PROPERTY_ROW_RE.match(line)
            if prop_match:
                result["properties"].append(prop_match.group(1))
        elif section == "methods":
            method_match = _REF_CLASS_METHOD_ROW_RE.match(line)
            if method_match:
                result["methods"].append(method_match.group(1))
    return result


_FULL_API_REF_SECTION_RE = re.compile(
    r"^##\s+API Reference\s*$(.*?)(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE
)
_PASCAL_CASE_TOKEN_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")


_API_REF_INTRO_BAD_A_RE = re.compile(r"ships \d+ public types\.\s*Selected entry points:", re.IGNORECASE)
_API_REF_INTRO_BAD_B_RE = re.compile(r"`\w[\w.]*\.\*`?\s*\.?\s*$")


def check_api_reference_classes_exist_in_reference_site(
    readme_text: str,
    reference_class_names: set[str] | None,
    clone_cache_root: str | None = None,
) -> list[dict]:
    """Hard gate (2026-08-09, MT027; absorbs the retired `check_api_reference_intro_names_
    classes`, 2026-08-05). Two checks on the `## API Reference` section, combined into one
    function because both answer the same underlying question -- "is this section's naming of
    real classes trustworthy" -- at two different strengths:

    1. **Bad-pattern detection** (the original 2026-08-05 heuristic, unchanged logic): the
       section's intro sentence must not be a bare "ships N public types. Selected entry
       points:" filler, nor a bare trailing `namespace.*`/`package.*` wildcard with no other
       backtick-quoted class name elsewhere in the sentence.
    2. **Real class-name verification** (new, 2026-08-09): every class name cited anywhere in
       the section (the established `` - `ClassName` [— description] `` bullet convention, plus
       any backtick-quoted PascalCase token in the intro sentence) must be confirmed by AT LEAST
       ONE of two independent real sources: this product's own `reference.aspose.org` class
       index (`reference_class_names`, the flattened `parse_reference_api_index` output), or a
       real class/struct/interface declaration in the clone-cache source (`clone_cache_root`,
       reusing `_find_class_source_files` -- the same lookup `check_named_member_accuracy`
       already uses). This is strictly stronger than (1): a sentence can pass the bad-pattern
       check by naming a class, while that class is fabricated -- (1) alone would never catch
       that; this closes the gap, extending this plan's "fabricated capability is the single
       worst defect class" principle (already enforced for diagram nodes and format claims) to
       API Reference class citations.

       **Two sources, not one, found live during this function's own Phase 1 pilot sanity pass
       (2026-08-09) -- not assumed correct on the first design.** A single-source design
       (reference-index-only) produced real false positives: `tex/python`'s `FontManager`/
       `FontMetrics`/`InputSource` and `pdf/cpp`'s `IIndexBitmapConverter`/`Pages` are genuine,
       already-source-verified real classes (confirmed during this plan's own earlier
       Verification-pass work) that simply don't appear in `reference.aspose.org`'s own
       generated index for those products -- real coverage gaps in an otherwise-graded source,
       the same "even structured/graded content isn't infallible" lesson `formats.md` already
       taught this plan (MT025's Twelfth incident), now confirmed to recur for reference-site
       coverage too. A class is only flagged as fabricated when NEITHER source confirms it.

    Elevated from (1)'s original heuristic status to a full hard gate now that (2), with its
    two-source corroboration, makes "is a named class real" reliably decidable, not just a
    content-quality judgment call -- the same class of elevation this plan already gave
    `check_process_narration_smells`.

    Class-name verification degrades gracefully when ONE source is unavailable:
    `reference_class_names` empty/`None` and/or `clone_cache_root` absent/not-a-directory simply
    removes that source from consideration (never a hard failure on its own).

    **When BOTH sources are absent (TC-HARDEN-31, Twenty-Second incident / MT035) -- the
    guaranteed starting state of any genuinely new product, before `/repo-scout` has ever run
    and before a `reference.aspose.org` page exists -- this no longer silently skips
    verification.** The prior behavior produced zero findings for a section naming any number
    of classes, indistinguishable from "verified clean," exactly when this hard gate's real
    defenses (this function and `check_named_member_accuracy`) were least able to back that
    verdict up. Every backtick-quoted class cited via the established bullet convention now
    produces a real, named "verification unavailable" finding instead, mirroring
    `check_diagram_verified_format_claims`'s own "absence of corroborating sources disqualifies
    the claim" design -- a fabricated class name in a brand-new product's candidate can no
    longer pass this gate with zero findings.

    Returns a list of {"reason": ...} and/or {"class_name", "reason"} findings.
    """
    findings: list[dict] = []

    intro_section_match = _API_REF_SECTION_RE.search(readme_text)
    if intro_section_match:
        intro = intro_section_match.group(1)
        if _API_REF_INTRO_BAD_A_RE.search(intro):
            findings.append({
                "reason": "API Reference intro sentence is a bare type-count filler "
                          "('ships N public types. Selected entry points:') -- name the "
                          "product's real hub class(es) instead",
            })
        elif _API_REF_INTRO_BAD_B_RE.search(intro.strip()):
            other_backticks = _BACKTICK_MEMBER_RE.findall(intro)
            if len(other_backticks) <= 1:
                findings.append({
                    "reason": "API Reference intro sentence is a bare namespace/package "
                              "wildcard with no real class named elsewhere in the sentence",
                })

    clone_cache_path = Path(clone_cache_root) if clone_cache_root else None
    clone_cache_usable = bool(clone_cache_path and clone_cache_path.is_dir())
    sources_available = bool(reference_class_names or clone_cache_usable)

    section_match = _FULL_API_REF_SECTION_RE.search(readme_text)
    if section_match:
        section_text = section_match.group(1)
        # Deliberately scoped to the established `` - `ClassName` `` bullet convention ONLY
        # -- free-form intro-sentence prose was tried and removed (2026-08-09, found live
        # during the full-portfolio sanity pass): a bare backtick-quoted PascalCase token in
        # prose is genuinely ambiguous between "a class name" and "a property name" (C#/Java
        # properties are PascalCase too, no invocation parens to distinguish them from a
        # class the way a method call's "()" does -- pdf/net's real intro sentence "exposing
        # `Pages` (a `PageCollection` of `Page` objects)" cites a PROPERTY named Pages, not a
        # class) or "an unrelated built-in exception name mentioned in a caveat" (3d/python's
        # real "...raise `AttributeError` (for saving)" gotcha callout). The structured
        # bullet convention has no such ambiguity -- every `` - `ClassName` `` line is a
        # deliberate, unambiguous class citation by construction, which is exactly why
        # `check_named_member_accuracy` was already scoped to it alone.
        cited_classes: set[str] = set()
        for bullet_match in _CLASS_BULLET_RE.finditer(section_text):
            for cls in (bullet_match.group(2), bullet_match.group(3)):
                if cls:
                    cited_classes.add(cls)

        reference_upper = {c.upper() for c in (reference_class_names or set())}
        for cls in sorted(cited_classes):
            # Tolerate a fully-qualified citation (Java/Python-style "pkg.module.ClassName",
            # found live in note/python's real bullets) by also trying the bare last
            # dot-segment -- reference.aspose.org's own class table always uses bare names.
            # If that last segment isn't itself PascalCase (e.g. pdf/java's real
            # "org.aspose.pdf.drawing" package-grouping bullet -- "drawing" is a lowercase
            # package name, not a class), this isn't a real single-class citation at all;
            # skip it rather than force a same-shape comparison that can't succeed. This
            # exclusion applies regardless of source availability -- a package-grouping
            # bullet was never a class citation to begin with.
            bare = cls.rsplit(".", 1)[-1]
            if not _PASCAL_CASE_TOKEN_RE.match(bare):
                continue
            if not sources_available:
                # TC-HARDEN-31 (MT035): neither corroborating source exists -- this class
                # name is genuinely unverified, not "assumed clean." Named explicitly so a
                # human/agent knows exactly why, and what would resolve it.
                findings.append({
                    "class_name": cls,
                    "reason": f"'{cls}' is named in the API Reference section, but no "
                              "verification source is available for this product yet -- "
                              "neither a reference.aspose.org class index nor a real "
                              "clone-cache checkout exists (run /repo-scout to populate the "
                              "clone cache before this class-name claim can be trusted)",
                })
                continue
            if bare.upper() in reference_upper:
                continue
            if clone_cache_usable and _find_class_source_files(clone_cache_path, bare):
                continue  # confirmed real by the second source; reference index was just incomplete
            findings.append({
                "class_name": cls,
                "reason": f"'{cls}' is named in the API Reference section but is confirmed "
                          "by neither this product's reference.aspose.org class index nor "
                          "its real clone-cache source",
            })
    return findings


_README_API_MODULE_HEADER_RE = re.compile(r"^###\s+(.+?)\s*$")
_README_API_SUBHEADER_RE = re.compile(r"^####\s+(.+?)\s*$")
_DETAILED_MEMBER_REFERENCE_RE = re.compile(r"^####\s+Detailed Member Reference\s*$", re.IGNORECASE)


def _parse_readme_api_tables(section_text: str) -> dict[str, list[str]]:
    """Thirteenth incident / MT028 (2026-08-09). Parses the README's own `## API Reference`
    section body for the module-grouped `| Class | Description |` table(s) inserted above the
    untouched curated `#### Detailed Member Reference` bullets (the user's own chosen
    presentation: table added as new content, existing curated detail preserved unchanged
    below it). Returns `{module: [class_name, ...]}` -- a real `###` module header starts a new
    bucket; a `####` sub-header (`Interfaces`/`Enumerations`, when present) does NOT start a new
    bucket, since `reference_index` (this function's comparison target, from
    `parse_reference_api_index`) already folds those into their owning module too -- same
    keying scheme, so this parser mirrors it rather than introducing a second one. Parsing stops
    at the `#### Detailed Member Reference` marker -- everything after it is the pre-existing
    curated bullet content this design leaves completely untouched, out of scope here.
    """
    tables: dict[str, list[str]] = {}
    current_module: str | None = None
    for line in section_text.splitlines():
        if _DETAILED_MEMBER_REFERENCE_RE.match(line):
            break
        module_match = _README_API_MODULE_HEADER_RE.match(line)
        if module_match:
            current_module = module_match.group(1).strip()
            tables.setdefault(current_module, [])
            continue
        if _README_API_SUBHEADER_RE.match(line):
            continue  # Interfaces/Enumerations sub-header -- rows still fold into current_module
        if current_module is None:
            continue
        row_match = _REF_INDEX_TABLE_ROW_RE.match(line)
        if row_match:
            tables[current_module].append(row_match.group(1))
    return tables


def check_api_reference_table_completeness(
    readme_text: str, reference_index: dict[str, list[dict]] | None,
) -> list[dict]:
    """Hard gate (2026-08-09, Thirteenth incident / MT028). MT027 grounded API Reference
    *verification* in reference.aspose.org's own graded `_index.md` content but never adapted
    the section's *presentation* to match -- direct user review of `3d/java`'s candidate found
    the section byte-identical to its pre-MT027 shape. This check enforces the fix the user
    chose (via `AskUserQuestion`, this session): a real, module-grouped table mirroring
    `_index.md`'s own organization, inserted above the pre-existing, completely-unchanged
    curated member-detail bullets.

    Verifies the README's own table(s) (`_parse_readme_api_tables`) are a faithful, complete
    mirror of `reference_index` (`parse_reference_api_index`'s output) in both directions:
    a real module/class absent from the README's table is a finding (`missing_module`/
    `missing_class` -- drift or incomplete transcription), and a table module/class not present
    in `reference_index` is a finding (`unrecognized_module`/`unrecognized_class` -- the
    fabrication-guard direction; structurally unlikely since the table is meant to be a direct
    mirror of already-verified data, but checked rather than assumed).

    No-op (empty findings) when `reference_index` is empty/falsy -- a product with no real
    `_index.md` yet keeps today's intro+curated-bullets-only shape unchanged; nothing is
    required of it by this check.
    """
    if not reference_index:
        return []
    section_match = _FULL_API_REF_SECTION_RE.search(readme_text)
    if not section_match:
        return [{
            "reason": "missing_section",
            "detail": "reference.aspose.org has real API index data for this product, but the "
                      "README has no '## API Reference' section to hold its table",
        }]
    readme_tables = _parse_readme_api_tables(section_match.group(1))

    # A real `##` header in _index.md with zero class rows (e.g. "See Also", a bullet-list
    # cross-reference section, not a class table -- confirmed real via parse_reference_api_index's
    # own documented behavior of returning `[]` for such headers) is not a class-table module at
    # all and has nothing to mirror. Found live during this check's own Phase 1 pilot sanity pass
    # against tex/python's real content (2026-08-09) -- excluded here rather than assumed away.
    real_modules = {
        module: {row["class"] for row in rows}
        for module, rows in reference_index.items() if rows
    }
    table_modules = {module: set(classes) for module, classes in readme_tables.items()}

    # Module names are matched case-insensitively (2026-08-11): a real reference.aspose.org
    # module name can require a different heading-safe casing in the README's own `###` heading
    # (e.g. "glTF Format" -> "GLTF Format", per check_heading_title_case's own established GLTF
    # exception -- glTF's genuine spelling starts lowercase, which title-case headings cannot
    # satisfy) without that legitimate re-casing being flagged as a missing/unrecognized module.
    # Found live on 3d/typescript, the first product whose real module name itself needed this
    # treatment (every other product's real module names happen to already be title-case-safe).
    real_by_key = {module.casefold(): module for module in real_modules}
    table_by_key = {module.casefold(): module for module in table_modules}

    findings: list[dict] = []
    for key, module in real_by_key.items():
        real_classes = real_modules[module]
        if key not in table_by_key:
            findings.append({
                "module": module, "reason": "missing_module",
                "detail": f"real reference.aspose.org module '{module}' has no matching table "
                          "in the README's API Reference section",
            })
            continue
        table_module = table_by_key[key]
        for cls in sorted(real_classes - table_modules[table_module]):
            findings.append({
                "module": module, "class_name": cls, "reason": "missing_class",
                "detail": f"'{cls}' is a real class in reference.aspose.org's '{module}' module "
                          "but is absent from the README's table for that module",
            })

    for key, module in table_by_key.items():
        if key not in real_by_key:
            findings.append({
                "module": module, "reason": "unrecognized_module",
                "detail": f"README table module '{module}' does not correspond to any real "
                          "reference.aspose.org module for this product",
            })
            continue
        real_module = real_by_key[key]
        for cls in sorted(table_modules[module] - real_modules[real_module]):
            findings.append({
                "module": module, "class_name": cls, "reason": "unrecognized_class",
                "detail": f"'{cls}' appears in the README's '{module}' table but is not a real "
                          f"class in reference.aspose.org's '{real_module}' module",
            })
    return findings


def check_api_reference_table_no_duplicate_rows(readme_text: str) -> list[dict]:
    """Hard gate (TC-HARDEN-21, MT034/Twentieth incident, 2026-08-12). `check_api_reference_
    table_completeness` (above) verifies presence/absence against the reference-site index -- it
    has no concept of duplication WITHIN the candidate's own table. A real clean-room
    regeneration pilot found a real instance this check exists to catch: `cells/cpp`'s
    regenerated Enumerations table listed `DiagnosticSeverity` twice, verbatim, back-to-back --
    it passed `check_api_reference_table_completeness` cleanly (both occurrences are legitimate
    against the reference index; duplication is a separate, orthogonal defect).

    Reuses `_parse_readme_api_tables` (returns `{module: [class_name, ...]}` as a LIST, not a
    set -- duplicates within one module's own rows survive the parse, not silently collapsed) --
    no new table-parsing logic needed. An exact class-name duplicate within the same module's
    table is mechanically unambiguous, never a judgment call, so this is a hard gate, not a
    heuristic; two rows sharing the same DESCRIPTION text but different class names is not a
    defect and is never flagged.

    The counting logic itself now lives in `lib.api_table_dupes.find_duplicate_rows()`
    (TC-DUPIDX-01, 2026-08-12, ST-059) -- this check's own proof case (cells/cpp's
    `DiagnosticSeverity`) turned out to be live in reference.aspose.org's own `_index.md`, not
    just this composed README candidate, so `check_reference_index_structure.py` gained a
    sibling check using the same shared algorithm rather than a second, divergent copy of it.
    """
    section_match = _FULL_API_REF_SECTION_RE.search(readme_text)
    if not section_match:
        return []
    tables = _parse_readme_api_tables(section_match.group(1))
    return _find_duplicate_rows(tables)


# Broadened 2026-08-09 during this check's own Phase 1 pilot sanity pass against cells/cpp's
# real content: reference.aspose.org's filler-text generator has more than one shape, not just
# "Class with N methods..." -- confirmed real, same file: "Struct with 10 properties.",
# "Class in the Cells CPP API.", "Struct in the Cells CPP API." (the same fallback pattern
# applied to structs and to nested/iterator types with no extractable member count at all).
#
# Broadened again 2026-08-09 during the Phase 2 portfolio rollout: two independent agents
# (pdf/python, email/cpp) each separately found a fourth shape -- "Enum with N members."/
# "Class with N members." (abbreviated "members" wording, used when the generator can't
# extract a real method/property split) -- 6 confirmed instances in each of the two products,
# undetected by the prior pattern because it only recognized "Enumeration" (never the
# abbreviated "Enum") and only "methods"/"properties" (never "members").
_GENERIC_CLASS_DESCRIPTION_RE = re.compile(
    r"^(?:Class|Struct|Interface|Enum(?:eration)?)\s+"
    r"(?:with\s+\d+\s+methods?(?:\s+and\s+\d+\s+propert(?:y|ies))?"
    r"|with\s+\d+\s+propert(?:y|ies)"
    r"|with\s+\d+\s+members?"
    r"|in\s+the\s+.+?\s+API)\.?$",
    re.IGNORECASE,
)


def check_no_generic_class_description(readme_text: str) -> list[dict]:
    """Heuristic (2026-08-09, Thirteenth incident / MT028), non-blocking -- same two-tier
    posture as `check_process_narration_smells`. Flags any API Reference table row whose
    Description column is still reference.aspose.org's own generic, low-information filler
    text -- what its generator falls back to when it can't extract a real sentence ("Class with
    N methods and M properties."). Confirmed real: 10 instances in `3d/java`'s own `_index.md`
    alone (`FileFormat`, `Node`, `Scene`, `Transform`, `Vector3`, `Pose`, plus 3 `*Exporter`/
    `*Importer` classes). A hit prompts the composing agent to write a real, verified one-line
    description instead of copying the filler forward -- never a hard fail, since writing a good
    description is real editorial judgment, not a mechanically decidable property.
    """
    section_match = _FULL_API_REF_SECTION_RE.search(readme_text)
    if not section_match:
        return []
    findings = []
    for line in section_match.group(1).splitlines():
        if _DETAILED_MEMBER_REFERENCE_RE.match(line):
            break
        row_match = _REF_INDEX_TABLE_ROW_RE.match(line)
        if not row_match:
            continue
        class_name, description = row_match.group(1), row_match.group(2)
        if _GENERIC_CLASS_DESCRIPTION_RE.match(description.strip()):
            findings.append({
                "class_name": class_name,
                "reason": f"'{class_name}' table description is still reference.aspose.org's "
                          "generic filler text -- replace with a real, verified one-line "
                          "description",
            })
    return findings


# Heuristic, non-blocking (2026-08-09, found live during this check's own Phase 1 pilot sanity
# pass against html/python's real content -- a 5th confirmed instance, following cells/cpp's
# DisplayTextLocaleSupport row, of the same defect class: reference.aspose.org's description
# generator truncates mid-sentence, apparently wherever the original doc comment's example text
# broke its own table-cell parsing (a literal `[...]`/backtick example). All 5 confirmed
# instances end in the literal string "e.g." immediately before the closing table cell --
# `ProcessingInstruction`, `CommentToken`, `EndTagToken`, `StartTagToken` (html/python) plus
# `DisplayTextLocaleSupport` (cells/cpp, fixed by hand before this pattern was recognized as
# recurring). A description ending in "e.g." is essentially never a real, complete sentence.
#
# Known, disclosed gap (2026-08-09, Phase 2 rollout): the Batch 5 agent reported a 6th real
# truncated-description instance on pdf/python's `TextObject` row, cut off differently (mid
# clause, around a `` `BT` `` operator reference, not ending in "e.g.") and fixed it by hand.
# The original triggering text is not preserved anywhere (this content lives only in the
# gitignored, non-versioned `reports/repo-presenter/` tree, and the agent's fix already
# overwrote it) -- broadening this regex from a description alone, without the real triggering
# string to build and test against, would be exactly the kind of unverified guess this plan's
# own "verify against real content before trusting" discipline exists to prevent. Left
# unbroadened; flagged here for whoever next captures a fresh instance of this shape.
_TRUNCATED_DESCRIPTION_RE = re.compile(r"\be\.g\.?\s*$", re.IGNORECASE)


def check_no_truncated_class_description(readme_text: str) -> list[dict]:
    """Heuristic, non-blocking -- same two-tier posture as `check_no_generic_class_description`.
    Flags any API Reference table row whose Description column was truncated mid-sentence by
    reference.aspose.org's own generator (ends in "e.g." with no completing clause) -- a
    confirmed, recurring defect class, distinct from the generic-filler pattern (this is a
    *cut-off real sentence*, not a *fallback template*). A hit prompts the composing agent to
    write the real, complete description (verified against clone-cache source), the same
    remediation as a generic-filler finding.
    """
    section_match = _FULL_API_REF_SECTION_RE.search(readme_text)
    if not section_match:
        return []
    findings = []
    for line in section_match.group(1).splitlines():
        if _DETAILED_MEMBER_REFERENCE_RE.match(line):
            break
        row_match = _REF_INDEX_TABLE_ROW_RE.match(line)
        if not row_match:
            continue
        class_name, description = row_match.group(1), row_match.group(2)
        if _TRUNCATED_DESCRIPTION_RE.search(description.strip()):
            findings.append({
                "class_name": class_name,
                "reason": f"'{class_name}' table description appears truncated mid-sentence "
                          "(ends in 'e.g.' with no completing clause) -- replace with the real, "
                          "complete, verified description",
            })
    return findings


# Heuristic, non-blocking (2026-08-09, found live during the same Phase 1 pilot sanity pass that
# found check_no_truncated_class_description's defect class -- a third, distinct reference.
# aspose.org generator defect, not the same as truncation or generic filler). Confirmed real: 81
# instances in html/python's own `_index.md` alone, every real `HTMLXxxElement` class whose real
# RST docstring wraps an HTML-tag example in double backticks (`` `<address>` ``) -- the `<tag>`
# content is stripped somewhere in the source's own generation pipeline, leaving a bare, visibly
# broken empty double-backtick span (four consecutive backtick characters) in the rendered
# description, e.g. "HTML ```` element." instead of "HTML `<address>` element."
#
# Broadened 2026-08-09 during the Phase 2 portfolio rollout: slides/java surfaced the same
# generator defect in its narrower, single-backtick form -- a real Javadoc `{@code <tag>}` span
# collapses to an isolated, empty 2-backtick pair (e.g. "an OOXML `` element." for the real
# `AdjustValue` row, the stripped `<a:gd>` tag), not the 4-backtick double-span form. A bare
# "``" substring cannot distinguish this from the opening OR closing delimiter of a legitimate
# double-backtick span with real content (`` ``Convert(Stream, SaveFormat)`` `` -- its closing
# delimiter is immediately followed by whitespace just as often as an isolated empty pair is, so
# a local-context regex alone false-positives on every such closing delimiter (confirmed by a
# first attempt at this fix that did exactly that, caught by its own negative test before
# shipping). A legitimate double-backtick span always contributes exactly two "``" occurrences
# to its description (one open, one close); an isolated stripped-example pair contributes one,
# unpaired -- so the discriminator is a per-description parity count, not a regex, handled in
# `_has_stripped_example` below.
_STRIPPED_EXAMPLE_RE = re.compile(r"````")


def _has_stripped_example(description: str) -> bool:
    """True if `description` contains an empty double-backtick span (`` STRIPPED_EXAMPLE_RE
    ``) or an odd number of "``" occurrences -- a well-formed set of legitimate double-backtick
    spans always contributes an even count (open + close per span); an odd count means at least
    one "``" is unpaired, which only happens when reference.aspose.org's generator stripped a
    real example out of a single-backtick span, per the module-level comment above.
    """
    if _STRIPPED_EXAMPLE_RE.search(description):
        return True
    return description.count("``") % 2 == 1


def check_no_stripped_example_in_description(readme_text: str) -> list[dict]:
    """Heuristic, non-blocking -- same two-tier posture as `check_no_truncated_class_description`.
    Flags any API Reference table row whose Description column contains an empty double-backtick
    span (four consecutive backticks) -- reference.aspose.org's generator stripped a real
    bracketed example (almost always an HTML/XML tag like `<address>`) out of the source
    docstring, leaving a visibly broken artifact. A hit prompts the composing agent to restore
    the real example text (verified against clone-cache source), the same remediation as a
    truncated-description finding.
    """
    section_match = _FULL_API_REF_SECTION_RE.search(readme_text)
    if not section_match:
        return []
    findings = []
    for line in section_match.group(1).splitlines():
        if _DETAILED_MEMBER_REFERENCE_RE.match(line):
            break
        row_match = _REF_INDEX_TABLE_ROW_RE.match(line)
        if not row_match:
            continue
        class_name, description = row_match.group(1), row_match.group(2)
        if _has_stripped_example(description):
            findings.append({
                "class_name": class_name,
                "reason": f"'{class_name}' table description contains an empty backtick "
                          "span (a stripped example, almost always an HTML/XML tag) -- restore "
                          "the real example text from clone-cache source",
            })
    return findings


_ANY_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_DOCSTRING_LEAK_RE = re.compile(r'r"""|r\'\'\'|^\s*"""|^\s*\'\'\'', re.MULTILINE)


def check_no_leaked_docstring_artifacts(readme_text: str) -> list[dict]:
    # Heuristic, non-blocking (2026-08-09, MT027) -- same two-tier posture as
    # check_process_narration_smells. Flags a raw Python docstring delimiter (an r-prefixed
    # triple-double-quote or triple-single-quote, or a bare triple-quote at the start of a
    # line) appearing in prose OUTSIDE any fenced code block.
    #
    # Generalizes a real, confirmed defect: tex/python/_index.md's own TeXOptions row -- despite
    # being grade: A in this repo's own reference.aspose.org content -- has its Description
    # column start with a raw-string triple-quote prefix immediately before real prose text, a
    # leak from a Python docstring extraction step, undetected by whatever graded that file "A".
    # If MT027's design copies a reference-site description verbatim into README prose, this
    # tripwire stops that specific artifact from silently riding along -- the same "verify,
    # don't blindly trust even a graded/structured source" lesson formats.md already taught this
    # plan (MT025's Twelfth incident), recurring here for a different content type.
    #
    # Returns a list of {"snippet", "reason"} findings.
    prose_only = _ANY_FENCED_CODE_RE.sub("", readme_text)
    findings = []
    for match in _DOCSTRING_LEAK_RE.finditer(prose_only):
        line_start = prose_only.rfind("\n", 0, match.start()) + 1
        line_end = prose_only.find("\n", match.end())
        line_end = line_end if line_end != -1 else len(prose_only)
        findings.append({
            "snippet": prose_only[line_start:line_end].strip(),
            "reason": "prose appears to contain a leaked raw Python docstring delimiter "
                      f"({match.group(0)!r}) -- likely copied verbatim from a source-extracted "
                      "description without stripping docstring syntax",
        })
    return findings


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

    **TC-HARDEN-28 (Twenty-Second incident / MT035, 2026-08-12).** A real 12-product,
    69-finding portfolio audit found the "multiple different casings of the same bare word"
    branch (the `elif` below, for words with NO canonical registry entry) produces a 63%
    false-positive rate from two confirmed, distinct mechanisms, both concentrated inside the
    `## API Reference` section's MT028 table-and-bullet content: (a) a Title-Case `###`/`####`
    module heading (e.g. `### Css`, `### Dom`, mirroring `reference.aspose.org`'s own real
    module names) colliding with the SAME word used correctly, all-caps, in ordinary body
    prose elsewhere -- heading text was never excluded from this scan; (b) a real, deliberately
    dual-cased technical identifier documented inside a table description cell (a Word
    field-code keyword like `DATA`/`IF`, a PDF content-stream operator mnemonic like `sc`/`SC`,
    an emphatic English word used for emphasis inside a description like "do NOT match") that
    happens to share its spelling, in the opposite case, with an unrelated ordinary-English use
    of the same word elsewhere in the file. Excluding heading lines AND the whole `## API
    Reference` section from THIS branch's occurrence map closes both mechanisms -- verified
    against the real 12-product corpus to drop the false-positive count from 43 to 0 while
    leaving the ~24 genuine `canonical_casing`-branch findings (commercial-SDK PascalCase
    spelling like `Docx`/`Pdf`/`Html` leaking into that same table's description-cell prose,
    uncorrected against this repo's own established all-caps canonical form) completely
    unaffected -- that branch is UNCHANGED and still scans the FULL document, including the API
    Reference section, since it must keep catching drift there; only the no-canonical-entry
    `elif` branch narrows its own text.

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

    # canonical_casing branch's occurrence map: the FULL document, unchanged -- must still
    # catch real drift anywhere, including inside the API Reference section.
    occurrences: dict[str, set[str]] = {}
    for match in _BARE_WORD_RE.finditer(prose_only):
        word = match.group(1)
        key = word.upper()
        if key in _GENERIC_ACRONYM_STOPLIST and key not in canonical_casing:
            continue
        occurrences.setdefault(key, set()).add(word)

    # elif (no-canonical-entry) branch's occurrence map: the whole API Reference section
    # removed FIRST (it must be located while its own `## API Reference` heading is still
    # intact -- `_FULL_API_REF_SECTION_RE` anchors on that exact heading text), THEN heading
    # lines stripped from what remains (TC-HARDEN-28, above). Order matters: stripping
    # headings first would delete the `## API Reference` heading itself, leaving nothing for
    # the section matcher to anchor on -- confirmed live, this exact ordering bug initially
    # left words/net/pdf/java/pdf/net's real API-Reference-table false positives unfixed.
    heuristic_text = prose_only
    api_ref_match = _FULL_API_REF_SECTION_RE.search(heuristic_text)
    if api_ref_match:
        heuristic_text = heuristic_text[:api_ref_match.start()] + heuristic_text[api_ref_match.end():]
    heuristic_text = _ANY_HEADING_LINE_RE.sub("", heuristic_text)
    heuristic_occurrences: dict[str, set[str]] = {}
    all_caps_seen: set[str] = set()
    for match in _BARE_WORD_RE.finditer(heuristic_text):
        word = match.group(1)
        key = word.upper()
        if key in _GENERIC_ACRONYM_STOPLIST and key not in canonical_casing:
            continue
        heuristic_occurrences.setdefault(key, set()).add(word)
        if word.isupper() and len(word) >= 2:
            all_caps_seen.add(key)

    findings: list[dict] = []
    for key in sorted(set(canonical_casing) | all_caps_seen):
        if key in canonical_casing:
            variants = occurrences.get(key, set())
            if not variants:
                continue
            correct = canonical_casing[key]
            for variant in sorted(variants):
                if variant != correct:
                    findings.append({
                        "format": key, "found": variant, "canonical": correct,
                        "reason": "bare format-name casing does not match the canonical registry form",
                    })
        else:
            variants = heuristic_occurrences.get(key, set())
            if len(variants) > 1:
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


# --- Fourteenth incident / MT029 (2026-08-09): five visitor-facing content-quality rules ---
# (upstream-issue disclosure, Key Capabilities SEO, Scope and Limitations list format, dev/test
# artifact linkage) plus a general-purpose section-isolation idempotency gate.

_ANY_BACKTICK_TOKEN_RE = re.compile(r"`([^`]+)`")
_COUNT_PHRASE_RE = re.compile(r"\b\d+\s+of\s+(?:the\s+)?\d+\b", re.IGNORECASE)
# Stock built-in exception names, too generic/reusable on their own to safely fingerprint --
# see _extract_upstream_issue_fingerprints's own docstring for the confirmed real collision
# (3d/python's real NotImplementedError) this excludes.
_GENERIC_BACKTICK_EXCLUSIONS = {
    "NotImplementedError", "NotImplemented", "TypeError", "ValueError", "RuntimeError",
}


def _extract_upstream_issue_fingerprints(upstream_issues_text: str) -> list[set[str]]:
    """Per real `upstream-issues.md` `## {title}` entry, extract a set of specific, rare
    fingerprint tokens: every backtick-quoted exact term in the entry body (exception/error
    type names, class/method names, exact commands -- the schema's own `- **Evidence**:` line
    already uses backticks for these, confirmed real across every captured instance this
    session) and every `"N of M"`-shaped count phrase (`"35 of the 45"`, `"67 of 69"`). Returns
    one set per entry -- callers require 2+ concurring tokens from the SAME set before flagging
    a paragraph, so a single coincidentally-shared token (a class name legitimately mentioned
    elsewhere) is never enough on its own.

    Deliberately does NOT fingerprint the title's own prose words (an earlier design did, then
    was reverted -- 2026-08-09, found live during this check's own Phase 1 pilot rollout): a
    genuinely legitimate, non-forensic pointer sentence for `cells/go`'s real defect --
    "edit `examples/go.mod`'s version to a valid pseudo-version" -- shares the filename
    (1 backtick token) plus the generic word "version" with the real issue title ("...has an
    invalid version string..."), which alone would have wrongly tripped the 2-token threshold
    on exactly the kind of sentence this check exists to *allow*. Backtick tokens and count
    phrases are already sufficient to catch every confirmed real leak instance this session
    found (`tex/python`'s real case alone concurs on 6+ backtick/count tokens with zero title
    words needed) -- title prose is too generic to safely contribute to the same threshold.
    Also excludes `_GENERIC_BACKTICK_EXCLUSIONS` -- a small set of stock Python built-in
    exception names too generic/reusable to safely fingerprint on their own (2026-08-09, found
    live during this check's own Phase 1 pilot rollout on `3d/python`): a legitimate, accurate
    Scope-and-Limitations bullet describing FBX's own real stub methods ("`FbxExporter.save()`
    ... raise `NotImplementedError`") coincidentally shares `FbxExporter` + `NotImplementedError`
    with a DIFFERENT real entry's evidence (about COLLADA-export dispatch order, not FBX at
    all) purely because `NotImplementedError` is the standard, ubiquitous way any Python
    library signals "not implemented" -- it recurs legitimately across unrelated stub methods
    throughout a single product's own accurate Scope and Limitations, so it is not, on its own,
    a distinctive signal of forensic duplication.
    """
    fingerprints: list[set[str]] = []
    for match in re.finditer(
        r"^##\s+(.+?)\s*$(.*?)(?=^##\s|\Z)", upstream_issues_text, re.MULTILINE | re.DOTALL
    ):
        body = match.group(2)
        # INFORMATIONAL-severity entries excluded entirely (2026-08-09, found live during
        # this check's own Phase 1 pilot rollout -- cells/go's golang.org/x/crypto note,
        # cells/cpp's bundled-sample note, html/python's [js]-extra-on-Windows note): every
        # one of the 3 confirmed false positives beyond the earlier fixes traced to an
        # INFORMATIONAL entry, whose own schema definition ("doesn't block anything, still
        # worth knowing") makes it inherently more likely to describe tangential, reusable
        # product facts (a real package name, a real optional-extra name) rather than a
        # uniquely forensic defect narrative. Verified this is safe, not just convenient: all
        # 7 confirmed real leak instances this session found trace to a BLOCKING or
        # FUNCTIONAL-DEFECT entry -- zero to an INFORMATIONAL one.
        severity_match = re.search(r"\*\*Severity\*\*:\s*(\S+)", body)
        if severity_match and severity_match.group(1).upper() not in ("BLOCKING", "FUNCTIONAL-DEFECT"):
            continue
        tokens = set(_ANY_BACKTICK_TOKEN_RE.findall(body)) - _GENERIC_BACKTICK_EXCLUSIONS
        tokens |= {m.group(0) for m in _COUNT_PHRASE_RE.finditer(body)}
        if tokens:
            fingerprints.append(tokens)
    return fingerprints


def check_no_upstream_issue_leaked_into_readme(
    readme_text: str, upstream_issues_text: str
) -> list[dict]:
    """Hard gate (2026-08-09, Fourteenth incident / MT029, Items 1+3). Real, confirmed defect:
    a 30-product portfolio scan found 7 of 30 (23%) README candidates carrying forensic
    upstream-defect detail (exact error text, exact file/module counts, exact reproduction
    steps) that duplicates a real, matching entry already correctly recorded in the sibling
    `upstream-issues.md` -- in two structural forms, an explicit `> **Known issue:**`
    blockquote (`tex/python`, `cells/go`) and plain bold-lead-in prose with no blockquote at
    all (`3d/python`, `3d/java`, `3d/typescript`, `slides/java`, `words/net`). The prior
    defense, `check_process_narration_smells`, is a fixed historical phrase blocklist --
    structurally reactive, unable to catch a new incident phrased differently. This check is
    structural instead: it cross-references the README against upstream-issues.md's own real,
    structured entries (`_extract_upstream_issue_fingerprints`) rather than matching wording.

    A paragraph (fenced code blocks and the `## API Reference` section excluded -- real class
    names legitimately recur there without describing the defect) is flagged only when it
    contains 2 or more fingerprint tokens from the SAME upstream-issues.md entry -- a single
    shared token is not enough (see `_extract_upstream_issue_fingerprints`'s own docstring).

    No-op (empty findings) when `upstream_issues_text` is empty/absent, or has no entries with
    extractable fingerprints (e.g. a "No upstream issues identified." file) -- nothing to leak.

    Remediation is not always deletion: a real, actionable blocking command (e.g. `words/net`'s
    real NU1101 build failure) still needs a plain, non-forensic pointer sentence in context
    (matching `html/python`'s already-correct "see upstream-issues.md for the root cause"
    pattern) -- only the forensic *specificity* must never appear in the README itself.

    `## Installation` and `## Quick Start` are excluded from scanning, alongside `## API
    Reference` -- found necessary live during this check's own Phase 1 pilot rollout
    (`cells/cpp`): these sections exist specifically to give real, accurate instructions using
    real package/file names, so legitimate overlap with an upstream-issues.md entry's own
    evidence (which cites those same real names) is structurally expected there, not
    suspicious -- unlike Scope and Limitations or Development and Testing prose, whose job is
    to describe facts *about* the product, not to *be* a real, necessarily-specific set of
    instructions. `check_no_undisclosed_blocking_commands` already separately and more
    precisely guards the one real risk specific to these two sections (an undisclosed BLOCKING
    command shipped verbatim); this check's own job is prose narration, not exact commands.
    """
    if not upstream_issues_text:
        return []
    fingerprints = _extract_upstream_issue_fingerprints(upstream_issues_text)
    if not fingerprints:
        return []

    prose = _ANY_FENCED_CODE_RE.sub("", readme_text)
    # Badge rows (the top-of-file [![alt](img)](link) line(s)) cite real package
    # names/URLs by construction -- same "real reference, not narration" reasoning as
    # Installation/Quick Start below, but scoped to just the badge line(s) rather than the
    # whole preamble, since the preamble is also where the one real, confirmed leak instance
    # this check exists to catch (tex/python's top-of-file "Known issue" blockquote) actually
    # lived -- excluding the whole preamble would have hidden that real case. Found live
    # during this check's own Phase 1 pilot rollout (cells/cpp's real NuGet badge).
    prose = "\n".join(
        line for line in prose.splitlines() if _BADGE_ROW_MARKER not in line
    )
    sections = _split_into_sections(prose)
    for excluded_heading in ("API Reference", "Installation", "Quick Start"):
        if excluded_heading in sections:
            prose = prose.replace(sections[excluded_heading], "", 1)

    findings = []
    for unit in _iter_leak_scan_units(prose):
        for fp_set in fingerprints:
            hits = {tok for tok in fp_set if tok in unit}
            if len(hits) >= 2:
                findings.append({
                    "matched_tokens": sorted(hits),
                    "paragraph": unit.strip()[:200],
                    "reason": "this paragraph restates specific facts already recorded in "
                              "upstream-issues.md -- forensic defect detail must live only "
                              "there, never in the public README",
                })
    return findings


def _iter_leak_scan_units(prose_text: str) -> list[str]:
    """Split prose into independently-scannable units for `check_no_upstream_issue_leaked_
    into_readme`. Each bullet is its own unit when a blank-line-delimited block consists
    ENTIRELY of bullets (a pure bulleted list, no other prose mixed in) -- real bulleted
    content in this portfolio (Key Capabilities, Scope and Limitations) has no blank line
    between items, so treating a whole bulleted section as one blank-line-delimited paragraph
    let an unrelated match in one bullet get misattributed to a completely different,
    unrelated bullet's text (found live, `cells/go`, during this check's own Phase 1 pilot
    rollout -- a Key Capabilities bullet about `Workbook`/`Worksheet` was flagged because a
    LATER, unrelated bullet elsewhere in the same list happened to mention `go.mod`). A
    blockquote or ordinary prose paragraph, by contrast, IS one coherent multi-line claim and
    stays grouped as a single unit -- only a genuinely blank-line-delimited block that is
    ENTIRELY bullets gets split.

    A single bullet's own text commonly WRAPS across multiple physical lines (a `- ` marker
    line followed by one or more indented continuation lines with no `- ` prefix of their
    own) -- this is the normal, near-universal shape for any bullet longer than ~80
    characters throughout this portfolio's real Scope and Limitations sections. A prior
    version of this function required EVERY line in the block (including wrapped
    continuations) to itself start with `- `, so a single wrapped bullet anywhere in the
    block silently defeated the whole per-bullet split and collapsed the ENTIRE block back
    into one giant unit -- reintroducing the exact cross-bullet misattribution bug this
    function exists to prevent, just one level up (found live, `3d/net`/`3d/typescript`,
    2026-08-13: adding a real, accurate Watermark finding to `upstream-issues.md` tripped a
    false leak match against a completely unrelated, earlier Rendering bullet, because that
    bullet's own wrapped continuation line broke the per-line bullet check for the whole
    Scope and Limitations block). Fixed by grouping each `- `-prefixed line with any
    following non-`- `-prefixed, non-blank lines as ONE bullet unit, and only falling back to
    treating the whole block as one unit when a non-blank line appears BEFORE any bullet has
    started (i.e. the block genuinely isn't a bulleted list at all).
    """
    units: list[str] = []
    for block in re.split(r"\n\s*\n", prose_text):
        if not block.strip():
            continue
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines or not lines[0].lstrip().startswith("- "):
            units.append(block)
            continue
        bullets: list[str] = []
        current: "list[str] | None" = None
        for line in lines:
            if line.lstrip().startswith("- "):
                if current is not None:
                    bullets.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current is not None:
            bullets.append("\n".join(current))
        units.extend(bullets)
    return units


_KEY_CAPABILITIES_SECTION_RE = re.compile(
    r"^##\s+Key Capabilities\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE
)


def check_key_capabilities_quality(readme_text: str) -> list[dict]:
    """Heuristic, non-blocking (2026-08-09, MT029 Item 2). A 6-product sample found Key
    Capabilities prose already reasonably strong (full sentences, real keywords, natural
    language) but with two real, recurring quality issues: bullet count too thin/fragmented,
    and 3+ bullets sharing the same near-duplicate opening (the confirmed `words/python`
    shape -- three separate single-clause "Load X via Y" bullets for DOCX/DOC/RTF that read as
    a broken-apart enumeration rather than distinct capabilities). Flags, never blocks --
    "is this bullet well-composed" is editorial judgment, the same two-tier posture as every
    other prose-quality check in this module.
    """
    section_match = _KEY_CAPABILITIES_SECTION_RE.search(readme_text)
    if not section_match:
        return []
    bullets = re.findall(r"^-\s+(.+)$", section_match.group(1), re.MULTILINE)
    findings: list[dict] = []
    if not (4 <= len(bullets) <= 12):
        findings.append({
            "reason": f"{len(bullets)} bullet(s) -- outside the healthy 4-12 range (too thin "
                      "to be useful, or too fragmented/duplicative)",
        })
    # First-word grouping, not a 2-word prefix -- the real words/python instance is "Load
    # DOCX documents...", "Load legacy DOC files...", "Load RTF files...": the same opening
    # VERB with a different 2nd word every time, which a 2-word-prefix key would never group
    # together at all. Found via this check's own test suite before trusting it on real
    # content, not assumed correct on the first design.
    openings: dict[str, list[str]] = {}
    for bullet in bullets:
        words = bullet.split()
        key = words[0].lower() if words else ""
        if key:
            openings.setdefault(key, []).append(bullet)
    for key, group in openings.items():
        if len(group) >= 3:
            findings.append({
                "reason": f"{len(group)} bullets all open with '{key}' -- likely fragmented "
                          "single-format bullets that should consolidate into one",
                "bullets": group,
            })
    for bullet in bullets:
        if len(bullet) < 40 and "`" not in bullet:
            findings.append({"reason": "thin bullet (<40 chars, no backtick-quoted keyword)", "bullet": bullet})
    return findings


_SCOPE_LIMITATIONS_SECTION_RE = re.compile(
    r"^##\s+Scope and Limitations\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE
)
# Broadened 2026-08-09 during the Phase 2 portfolio rollout: the original pattern only matched
# the Java/C# stub-exception convention (`NotImplementedException`), silently missing Python's
# idiomatic `NotImplementedError` -- a real, disclosed false-negative gap for every Python
# product in this portfolio (found via words/python's real "`LdmDocxWriter` has a documented
# `NotImplementedError`..." Scope-and-Limitations bullet, which never registered as a stub
# bullet under the prior pattern).
_STUB_INDICATOR_RE = re.compile(
    r"\bNotImplementedException\b|\bNotImplementedError\b|\bnot implemented\b"
    r"|\bnot yet implemented\b|\bstub\b|\bthrows\b",
    re.IGNORECASE,
)


def check_capability_scope_contradiction(readme_text: str) -> list[dict]:
    """Heuristic, non-blocking (2026-08-09, MT029 Item 2). Real, confirmed motivating case:
    `3d/net`'s Key Capabilities claimed "Embed or extract text watermarks... via the
    `Watermark` utility class" while its own `Watermark.cs` source has every `EncodeWatermark`/
    `DecodeWatermark` overload unconditionally `throw new NotImplementedException(...)` -- and
    its own Scope and Limitations already correctly documented this. No check previously
    cross-referenced these two sections against each other.

    Extracts the first backtick-quoted token from every Key Capabilities bullet, reduces it to
    a bare keyword (strips any `.method`/`(args)` suffix), and case-insensitively substring-
    matches that keyword against every Scope-and-Limitations bullet containing a stub-
    indicating phrase -- a *substring* match, not an exact backtick-token match, because the
    real motivating case describes the stub in plain prose, not backticks: `3d/net`'s real
    Scope-and-Limitations text is "...and text-watermark encode/decode" (no backticks at all)
    while Key Capabilities names the class as `` `Watermark` ``; an exact-token design would
    have missed this real instance entirely, confirmed by testing against the real file before
    finalizing this design, not assumed to work. Deliberately coarse and heuristic -- a class
    can legitimately be mostly-supported with one specific stub method, which this substring
    check cannot distinguish from a genuine contradiction; it exists to prompt the same
    judgment pass that would have caught the real `3d/net` instance, not to auto-block on
    every hit.
    """
    caps_match = _KEY_CAPABILITIES_SECTION_RE.search(readme_text)
    scope_match = _SCOPE_LIMITATIONS_SECTION_RE.search(readme_text)
    if not caps_match or not scope_match:
        return []
    cap_bullets = re.findall(r"^-\s+(.+)$", caps_match.group(1), re.MULTILINE)
    scope_bullets = re.findall(r"^-\s+(.+)$", scope_match.group(1), re.MULTILINE)
    stub_bullets = [b for b in scope_bullets if _STUB_INDICATOR_RE.search(b)]

    findings = []
    for bullet in cap_bullets:
        cap_tokens = _ANY_BACKTICK_TOKEN_RE.findall(bullet)
        if not cap_tokens:
            continue
        keyword = re.split(r"[.(]", cap_tokens[0])[0]
        if len(keyword) < 4:
            continue
        keyword_re = re.compile(re.escape(keyword), re.IGNORECASE)
        for stub_bullet in stub_bullets:
            if keyword_re.search(stub_bullet):
                findings.append({
                    "capability_bullet": bullet,
                    "matched_keyword": keyword,
                    "scope_bullet": stub_bullet,
                    "reason": f"'{keyword}' is named as a working capability here, but a "
                              "Scope and Limitations bullet documents related functionality "
                              "as not-implemented/stub -- verify this isn't a fabricated-"
                              "capability contradiction",
                })
                break
    return findings


def check_scope_limitations_format(readme_text: str) -> list[dict]:
    """Hard gate (2026-08-09, MT029 Item 4). A 6-product sample found 0 of 6 using a bulleted
    list -- 5 of 6 were prose paragraphs, and the 1 real exception (`pdf/net`) already showed
    the target shape: a bulleted list (optionally with bold category sub-labels once there are
    enough items to group) followed by a plain-prose closing paragraph linking the Enterprise
    Edition. This check enforces that shape portfolio-wide -- it does not invent a new format,
    it generalizes the one real product that already had it right.

    Findings:
    - `not_a_list`: the section has no `- ` bulleted lines at all (the old prose-paragraph
      shape).
    - `enterprise_paragraph_is_bulleted`: the closing Enterprise-mention content is itself a
      bullet -- violates the user's explicit "this para should remain as it is" instruction
      (a plain paragraph, not absorbed into the limitations list).
    - `missing_enterprise_paragraph`: no plain-prose paragraph linking a real
      `products.aspose.com` Enterprise Edition URL follows the limitations list.
    """
    section_match = _SCOPE_LIMITATIONS_SECTION_RE.search(readme_text)
    if not section_match:
        return []
    lines = [line for line in section_match.group(1).splitlines() if line.strip()]
    if not lines:
        return [{"reason": "empty_section", "detail": "Scope and Limitations section is empty"}]

    bullet_lines = [line for line in lines if line.lstrip().startswith("- ")]
    if not bullet_lines:
        return [{
            "reason": "not_a_list",
            "detail": "Scope and Limitations must be a bulleted list (one distinct limitation "
                      "per '- ' line), not prose paragraphs",
        }]

    # Classify by content, not position -- an earlier position-based design ("everything
    # after the last bullet is the trailing paragraph") could not tell "no enterprise
    # paragraph at all" apart from "the enterprise mention IS itself the last bullet" (both
    # produce an empty trailing region); found via this check's own test suite before
    # trusting it on real content, not assumed correct on the first design.
    non_bullet_lines = [line for line in lines if not line.lstrip().startswith("- ")]
    enterprise_in_bullet = any(_ENTERPRISE_LINK_HOST_RE.search(line) for line in bullet_lines)
    enterprise_in_prose = any(_ENTERPRISE_LINK_HOST_RE.search(line) for line in non_bullet_lines)

    findings = []
    if enterprise_in_bullet:
        findings.append({
            "reason": "enterprise_paragraph_is_bulleted",
            "detail": "the closing Enterprise Edition paragraph must stay plain prose, not be "
                      "absorbed into the limitations list",
        })
    elif not enterprise_in_prose:
        findings.append({
            "reason": "missing_enterprise_paragraph",
            "detail": "Scope and Limitations must close with a plain-prose paragraph linking "
                      "the Enterprise Edition",
        })
    return findings


def check_dev_test_artifacts_linked(readme_text: str, detected_artifacts: list[dict]) -> list[dict]:
    """Hard gate (2026-08-09, MT029 Item 5). An 8-product clone-cache audit found real,
    recurring gaps: `AGENTS.md`/`agents.md` present but unlinked in 4 of 5 applicable repos;
    real in-repo `docs/*.md` guides, `PUBLIC_API.md`, `CHANGELOG.md`, `PUBLISHING.md` never
    referenced at all (`pdf/java`: 9 real docs files, 0 linked); nested test/example
    `README.md` files unlinked in 3 of 8. Categories confirmed absent from every sampled repo
    (`CONTRIBUTING.md`, `tox.ini`, `noxfile.py`, `Makefile`, `.coveragerc`,
    `CODE_OF_CONDUCT.md`, root `SECURITY.md`) are correctly never required -- `detected_
    artifacts` (from `_detect_dev_test_artifacts`) only ever contains real, on-disk paths,
    never invented ones, matching this plan's "link IF it exists, never guess" discipline.

    A detected artifact counts as linked when its relative path or basename appears inside
    some real markdown link href in the README (not just prose mention). No-op when
    `detected_artifacts` is empty.
    """
    if not detected_artifacts:
        return []
    hrefs = {href for _, href in _MD_LINK_RE.findall(readme_text)}
    findings = []
    for artifact in detected_artifacts:
        path = artifact["relative_path"]
        basename = path.rsplit("/", 1)[-1]
        if any(path in href or basename in href for href in hrefs):
            continue
        findings.append({
            "path": path, "kind": artifact.get("kind"),
            "reason": f"real artifact '{path}' exists in the source repo but is not linked "
                      f"anywhere in the README (expected in '{artifact.get('section')}')",
        })
    return findings


_DEV_TESTING_SECTION_RE = re.compile(
    r"^##\s+Development and Testing\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE
)


def check_development_testing_collapse(readme_text: str) -> list[dict]:
    """Heuristic, non-blocking (2026-08-09, MT029 Item 5). Generalizes the same "brief,
    always-visible summary + `<details>` for the rest" shape already proven twice in this
    plan (`## Additional Examples`'s flagship-example rule; this session's own MT028 API-
    Reference-table + Detailed-Member-Reference split) to `## Development and Testing` --
    once real artifact linking (`check_dev_test_artifacts_linked`) can add several links plus
    multiple real test/lint/build commands, the section risks the same "wall of detail with
    nothing collapsed" shape those two precedents already fixed elsewhere.

    Flags a section with more than 2 fenced code blocks or 3+ linked artifacts and no
    `<details>` wrapper at all -- a prompt to restructure, not an automatic fail, since a
    genuinely short section (one install command, one test command) never needs collapsing.
    """
    section_match = _DEV_TESTING_SECTION_RE.search(readme_text)
    if not section_match:
        return []
    body = section_match.group(1)
    if "<details>" in body:
        return []
    fenced_count = len(_ANY_FENCED_CODE_RE.findall(body))
    link_count = len(_MD_LINK_RE.findall(body))
    if fenced_count > 2 or link_count >= 3:
        return [{
            "reason": f"Development and Testing has {fenced_count} code block(s) and "
                      f"{link_count} linked artifact(s) with no <details> wrapper -- consider "
                      "a brief always-visible summary + collapsed detail, matching the "
                      "Additional Examples / API Reference sections' established pattern",
        }]
    return []


def _split_into_sections(markdown_text: str) -> dict[str, str]:
    """Split into `{heading_text: full_section_text_including_heading}`, plus a
    `"__preamble__"` key for everything before the first `##` heading (title, badges, banner,
    intro paragraph). Only `##` (H2) headings are section boundaries -- `###` subsections stay
    inside their owning `##` section's text, which is exactly what "did this section change"
    should mean for `check_only_sections_changed`.
    """
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", markdown_text, re.MULTILINE))
    sections: dict[str, str] = {}
    preamble_end = matches[0].start() if matches else len(markdown_text)
    sections["__preamble__"] = markdown_text[:preamble_end]
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
        sections[match.group(1).strip()] = markdown_text[start:end]
    return sections


def check_only_sections_changed(
    old_markdown_text: str, new_markdown_text: str, allowed_headings: list[str]
) -> list[dict]:
    """General-purpose section-isolation hard gate (2026-08-09, MT029 idempotency
    requirement), generalizing `check_only_mermaid_block_changed`'s (MT021/MT024) proof
    technique from one hardcoded region (the Mermaid block) to any named set of `##` sections.
    Pass `"__preamble__"` in `allowed_headings` to permit the region before the first `##`
    heading (title/badges/banner/intro paragraph) to change too -- needed for Items 1+3's
    known-issue relocation, which genuinely spans that preamble and Scope and Limitations
    together as one coordinated edit.

    Returns a list of `{"heading", "reason"}` findings for every section OUTSIDE
    `allowed_headings` whose text differs between old and new (including a section added or
    removed entirely) -- empty iff every section not named in `allowed_headings` is
    byte-identical. Unlike the boolean `check_only_mermaid_block_changed`, this returns
    structured findings naming exactly which section unexpectedly changed -- a deliberate
    API improvement for a check now used across many different single- and multi-section
    edits, not a regression from the earlier function's shape.
    """
    old_sections = _split_into_sections(old_markdown_text)
    new_sections = _split_into_sections(new_markdown_text)
    allowed = set(allowed_headings)
    findings = []
    for heading in set(old_sections) | set(new_sections):
        if heading in allowed:
            continue
        if old_sections.get(heading) != new_sections.get(heading):
            findings.append({
                "heading": heading,
                "reason": "section changed but is not in the declared allowed_headings set "
                          "for this edit",
            })
    return findings


# ==================================================================================================
# Fifteenth incident / MT030 (2026-08-09): verify-and-merge of old-README prose.
#
# check_dropped_content (above) only ever tracked links and H2/H3 headings -- real, but a much
# narrower slice than "everything worth preserving in the old upstream README." A real 5-product
# survey (words/net, pdf/cpp, slides/java, email/cpp, note/python) confirmed a genuine,
# reproducible gap: mechanism-level explanations embedded in feature bullets (e.g. pdf/cpp's
# real font-fallback rationale, "so glyphs render even in fontless Linux/CI containers") and
# branding/positioning claims ("Official Aspose project") were silently compressed to bare facts
# or dropped without a trace, invisible to check_dropped_content because neither is a link or a
# heading. Per the user's own decision (AskUserQuestion, 2026-08-09): pure narrative/origin-
# story/CTA prose (a third pattern found in the same survey -- "Star it (star emoji)", "not set
# in stone") stays explicitly out of scope, same as today -- "verified against product repo"
# naturally scopes to checkable facts, not opinion/tone with nothing to verify against source.
#
# The functions below extract every real prose "content unit" from the old README (paragraph or
# top-level list item, whichever is smaller -- reusing check_no_upstream_issue_leaked_into_
# readme's own proven _iter_leak_scan_units segmentation rather than reimplementing it), then
# require the composing agent to record, for every single one, a real disposition in
# content-dispositions.json (merged into the new candidate, reframed to fit, or excluded with a
# verified reason) -- finally making real what `dropped_claims.json` only ever promised as a
# docstring aspiration since 2026-08-04.
# ==================================================================================================

_CATEGORY_1_PHRASE_RE = re.compile(
    r"\bstar it\b|\bgive .{0,15}a star\b|\bnot set in stone\b|\bstay tuned\b|\bcoming soon\b"
    r"|\bjoin us\b|\bour journey\b|\bwe'?re excited\b|\bthe final shape\b",
    re.IGNORECASE,
)
# A conservative, deliberately small emoji range -- common decorative/CTA emoji (star, party,
# rocket, checkmark, etc.), not an exhaustive Unicode-emoji sweep. A miss here just means a unit
# doesn't get the prefilter hint; it is never excluded outright (see the docstring below).
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF☀-➿⬀-⯿❤️]"
)


def _likely_category_1_signal(excerpt: str) -> bool:
    """Cheap, deliberately disclosed-incomplete prefilter for narrative/origin-story/CTA prose
    (category 1, out of scope per the user's own 2026-08-09 decision). NEVER used to delete or
    exclude a content unit at extraction time -- only stored as a hint field
    (`likely_category_1_prefilter`) feeding `check_content_unit_classification_plausibility`'s
    non-blocking cross-check below. Tone/purpose classification is a judgment call this project
    has consistently never pretended a regex can make on its own (same posture as
    `check_process_narration_smells`'s own fixed-phrase-list limitation).
    """
    if _EMOJI_RE.search(excerpt):
        return True
    if _CATEGORY_1_PHRASE_RE.search(excerpt):
        return True
    return excerpt.count("!") >= 2


_SALIENT_BACKTICK_RE = re.compile(r"`([^`]+)`")
_SALIENT_IDENTIFIER_RE = re.compile(r"\b(?:[A-Za-z]+[A-Z][A-Za-z0-9]*|[A-Z]{2,}[A-Za-z0-9]*)\b")
_SALIENT_VERSION_RE = re.compile(r"\b\d+(?:\.\d+){1,3}\b")
_SALIENT_QUOTED_RE = re.compile(r'"([^"]{2,40})"')


def _extract_salient_tokens(excerpt: str) -> list[str]:
    """Seed extractor for a content unit's checkable identity -- backtick spans, CamelCase/
    ALLCAPS identifier-shaped tokens, quoted names, version numbers. Explicitly disclosed as
    incomplete, same posture as `_DIAGRAM_SUPPLEMENTARY_FORMAT_NAMES`/
    `_CONTAINER_CONNECTOR_ALLOWLIST` elsewhere in this module -- exists to give
    `check_content_unit_merged_into_target_section` something mechanically checkable, not to
    summarize meaning. Order-preserving, case-insensitive de-duplication.
    """
    tokens: list[str] = []
    for pattern in (_SALIENT_BACKTICK_RE, _SALIENT_IDENTIFIER_RE, _SALIENT_VERSION_RE, _SALIENT_QUOTED_RE):
        tokens.extend(pattern.findall(excerpt))
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        token = token.strip()
        if token and token.lower() not in seen:
            seen.add(token.lower())
            ordered.append(token)
    return ordered


_ANY_HEADING_LINE_RE = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)
# 2026-08-10, MT030 Phase 2: replaces an earlier flat len(excerpt) < 25 noise filter, which
# silently dropped real, substantive short bullets. See extract_old_readme_content_units's own
# docstring for the real, confirmed instances this fixes.
_CONTENT_UNIT_SIGNIFICANT_WORD_RE = re.compile(r"[A-Za-z]{4,}")


def extract_old_readme_content_units(old_readme_text: str) -> list[dict]:
    """Mechanical segmentation of the old upstream README's real PROSE into checkable "content
    units" -- the extraction half of the verify-and-merge upgrade. `_old_readme_inventory`
    (readme_refresh_run.py) already tracks links and headings separately; this covers
    everything else. Granularity: paragraph-or-top-level-list-item, whichever is smaller --
    justified directly against the real survey evidence this design was built from (words/net's
    origin story is a blank-line-delimited paragraph; pdf/cpp's font-fallback rationale and
    note/python's pypdf dependency both live inside single bullet lines).

    Heading lines (of any level -- already owned by `_HEADING_RE`/`_old_readme_inventory` for
    H2/H3, and an old README's H1 title needs no separate tracking), fenced code blocks, and
    badge-row lines are stripped before segmentation. Reuses `_iter_leak_scan_units`'s proven
    paragraph-vs-pure-bulleted-block splitting logic rather than reimplementing it. A unit with no
    word of 4+ letters is dropped as noise (a stray short word, a lone "---", punctuation-only
    fragments) -- deliberately NOT a flat character-count floor. A prior `len(excerpt) < 25`
    version of this filter was found live during MT030 Phase 2 (2026-08-10) to silently drop real,
    substantive short capability-list bullets -- confirmed on 2 products independently:
    `cells/cpp`'s "- Cells and formulas"/"- Document properties" and `cells/java`'s "- Merged
    cells"/"- Defined names"/"- Hyperlinks"/"- Data validation"/"- Conditional formatting"/"- Page
    setup"/"- Worksheet protection" (9 real bullets total, none ever reachable for MT030/MT031
    recovery). The word-based rule keeps every one of those (each has a 4+-letter word) while still
    correctly dropping the original noise cases ("---" has zero letters; "Ok." has only "Ok", 2
    letters).

    Returns `[{"unit_id", "excerpt", "salient_tokens", "likely_category_1_prefilter"}, ...]` in
    extraction order. `unit_id` is a stable, order-based id (`u0001`, `u0002`, ...), not a
    content hash -- it survives whitespace-only re-runs the same way `_old_readme_inventory`'s
    existing sorted link/heading lists already do. Category-1 (narrative/CTA) content is NOT
    excluded here -- every unit, however obviously narrative, still needs a real disposition
    entry; see `_likely_category_1_signal`'s own docstring for why that classification stays a
    judgment call, never a mechanical filter, at extraction time.
    """
    no_code = _ANY_FENCED_CODE_RE.sub("", old_readme_text)
    no_headings = _ANY_HEADING_LINE_RE.sub("", no_code)
    prose_lines = [line for line in no_headings.splitlines() if _BADGE_ROW_MARKER not in line]
    prose_text = "\n".join(prose_lines)

    units: list[dict] = []
    for raw_excerpt in _iter_leak_scan_units(prose_text):
        excerpt = raw_excerpt.strip()
        if not _CONTENT_UNIT_SIGNIFICANT_WORD_RE.search(excerpt):
            continue
        units.append({
            "unit_id": f"u{len(units) + 1:04d}",
            "excerpt": excerpt,
            "salient_tokens": _extract_salient_tokens(excerpt),
            "likely_category_1_prefilter": _likely_category_1_signal(excerpt),
        })
    return units


_CONTENT_UNIT_CLASSIFICATIONS = frozenset({
    "1_narrative_cta", "2_mechanism_explanation", "3_branding_positioning", "redundant_with_existing",
    "4_verifiable_history",
})
_CONTENT_UNIT_DISPOSITIONS = frozenset({"merged_verbatim", "merged_reframed", "excluded"})
_CONTENT_UNIT_VERIFICATION_STATUSES = frozenset({
    "verified_against_source", "verified_redundant", "not_applicable_category_1",
    "verified_by_corroboration",
})
# "Project History" (2026-08-10, MT031/Sixteenth incident): a new, permanently OPTIONAL H3
# section for genuine, checkable project/format history that doesn't belong in Scope and
# Limitations or Intro -- deliberately NOT added to _REQUIRED_SECTIONS (matching the existing
# "## Additional Examples" precedent of an optional section that's vacuously satisfied when a
# product has nothing real for it). H3, not H2, is load-bearing: _split_into_sections/
# check_required_sections/check_only_sections_changed all split only on "^##" (H2) -- an H3
# heading stays inside "__preamble__" alongside the unheaded Intro paragraph, so no downstream
# section-boundary code needed to change. check_content_unit_merged_into_target_section maps
# both "Intro" and "Project History" to the same "__preamble__" section body.
_CONTENT_UNIT_TARGET_SECTIONS = frozenset(_REQUIRED_SECTIONS) | {"Intro", "Project History"}


def check_content_unit_disposition_coverage(
    content_units: list[dict], dispositions: list[dict]
) -> list[dict]:
    """Hard gate. Every content unit `extract_old_readme_content_units` finds in the old README
    must have exactly one, well-formed disposition entry in `content-dispositions.json` -- the
    coverage half of finally making real what `dropped_claims.json` only ever promised (this
    module's own docstrings referenced it from 2026-08-04 through 2026-08-09; no code ever
    implemented it). Absence is never "trust it" here: if real content units exist, an empty or
    missing `content-dispositions.json` is a hard-gate failure, not a silent default -- mirroring
    `check_dropped_content`'s own precedent of a correctly-vacuous pass only when there is
    genuinely nothing to account for (i.e. `content_units` is itself empty).

    Checks: every `unit_id` has exactly one entry (no missing, no dupes, no dangling references
    to a `unit_id` absent from `content_units`); `classification`/`disposition` are valid enum
    values; a `merged_*` entry has a `target_section` in
    `_REQUIRED_SECTIONS | {"Intro", "Project History"}`; an `excluded` entry has a real
    `excluded_reason` (>=15 chars, not a placeholder); every entry whose `classification` is not
    `1_narrative_cta` must carry `verification.status != not_applicable_category_1` plus a
    non-empty `verification.evidence_ref` -- an "excluded because it's no longer true"
    disposition is itself a verified claim and must cite where that was confirmed, the same as a
    merge. `4_verifiable_history` entries must use `verification.status ==
    verified_by_corroboration` (2026-08-10, MT031) -- a real but categorically weaker standard
    than `verified_against_source` (genuine project/format history describes a past event no
    current source state can prove or disprove the way a live mechanism claim can be compiled/
    grepped against; "verified" here means internally consistent with, not contradicted by, real
    repo artifacts -- never "proven"), so the two statuses must never be interchangeable.
    """
    findings: list[dict] = []
    unit_ids = {unit["unit_id"] for unit in content_units}
    seen_ids: set[str] = set()
    by_id: dict[str, dict] = {}
    for entry in dispositions:
        uid = entry.get("unit_id")
        if uid in seen_ids:
            findings.append({"unit_id": uid, "reason": "duplicate disposition entry for the same unit_id"})
            continue
        seen_ids.add(uid)
        by_id[uid] = entry
        if uid not in unit_ids:
            findings.append({
                "unit_id": uid,
                "reason": "disposition references a unit_id not present in the current old-README extraction",
            })

    for uid in unit_ids:
        entry = by_id.get(uid)
        if entry is None:
            findings.append({"unit_id": uid, "reason": "no disposition entry -- every extracted content unit needs one"})
            continue
        classification = entry.get("classification")
        disposition = entry.get("disposition")
        if classification not in _CONTENT_UNIT_CLASSIFICATIONS:
            findings.append({"unit_id": uid, "reason": f"invalid classification {classification!r}"})
        if disposition not in _CONTENT_UNIT_DISPOSITIONS:
            findings.append({"unit_id": uid, "reason": f"invalid disposition {disposition!r}"})
            continue
        if disposition in ("merged_verbatim", "merged_reframed"):
            target = entry.get("target_section")
            if target not in _CONTENT_UNIT_TARGET_SECTIONS:
                findings.append({
                    "unit_id": uid,
                    "reason": f"merged disposition needs a real target_section, got {target!r}",
                })
        else:  # excluded
            reason_text = (entry.get("excluded_reason") or "").strip()
            if len(reason_text) < 15:
                findings.append({
                    "unit_id": uid,
                    "reason": "excluded disposition needs a real excluded_reason (>=15 chars)",
                })
        verification = entry.get("verification") or {}
        status = verification.get("status")
        if status not in _CONTENT_UNIT_VERIFICATION_STATUSES:
            findings.append({"unit_id": uid, "reason": f"invalid verification.status {status!r}"})
        elif classification is not None and classification != "1_narrative_cta" and status == "not_applicable_category_1":
            findings.append({
                "unit_id": uid,
                "reason": "only category-1 (narrative/CTA) units may use verification.status="
                          "not_applicable_category_1",
            })
        elif classification == "4_verifiable_history" and status != "verified_by_corroboration":
            findings.append({
                "unit_id": uid,
                "reason": "4_verifiable_history units must use verification.status="
                          "verified_by_corroboration, not a stronger or unrelated status -- "
                          "history claims are corroborated, never proven the way a live "
                          "mechanism claim can be",
            })
        elif classification != "4_verifiable_history" and status == "verified_by_corroboration":
            findings.append({
                "unit_id": uid,
                "reason": "verification.status=verified_by_corroboration is reserved for "
                          "4_verifiable_history units",
            })
        elif status != "not_applicable_category_1" and not verification.get("evidence_ref"):
            findings.append({
                "unit_id": uid,
                "reason": "non-category-1 verification needs a non-empty evidence_ref",
            })
    return findings


def check_content_unit_evidence_resolves(
    dispositions: list[dict],
    clone_cache_root: str,
    package_registry: "dict | None" = None,
    docs_texts: "dict[str, str] | None" = None,
) -> list[dict]:
    """Hard gate. For every disposition entry whose verification cites real evidence (anything
    other than `not_applicable_category_1`), confirms the cited evidence actually resolves --
    reuses the same acquire-then-check-existence discipline as `check_license_link_target`/
    `_detect_license_file`. Confirms a citation EXISTS, never that it SUPPORTS the specific
    claim -- the same "presence, not proof" limit `check_named_member_accuracy` already
    discloses about itself.

    Dispatches on `verification.evidence_type`: `"clone_cache_path"` -> case-sensitive on-disk
    file existence under `clone_cache_root`; `"package_registry_field"` -> dotted-path walk of
    `package_registry` (e.g. `"cells.python.candidate"`); `"docs_reference"` -> membership check
    against `docs_texts`' keys (real doc paths already loaded by the caller, mirroring
    `_product_formats_md`/`_product_api_surface`'s "read once, hand in as text" pattern);
    `"candidate_section_reference"` (the `verified_redundant` case, pointing at another spot in
    the SAME new candidate rather than upstream source) is always treated as resolved here --
    its real verification is `check_content_unit_merged_into_target_section` below, not this
    function, per this evidence type's own design.
    """
    package_registry = package_registry or {}
    docs_texts = docs_texts or {}
    root = Path(clone_cache_root)
    findings: list[dict] = []
    for entry in dispositions:
        verification = entry.get("verification") or {}
        if verification.get("status") == "not_applicable_category_1":
            continue
        evidence_type = verification.get("evidence_type")
        evidence_ref = verification.get("evidence_ref")
        if not evidence_ref:
            continue  # already flagged by check_content_unit_disposition_coverage
        if evidence_type == "clone_cache_path":
            resolved = (root / evidence_ref).is_file()
        elif evidence_type == "package_registry_field":
            node = package_registry
            resolved = True
            for part in evidence_ref.split("."):
                if isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    resolved = False
                    break
        elif evidence_type == "docs_reference":
            resolved = evidence_ref in docs_texts
        elif evidence_type == "candidate_section_reference":
            resolved = True
        else:
            findings.append({
                "unit_id": entry.get("unit_id"),
                "reason": f"unrecognized verification.evidence_type {evidence_type!r}",
            })
            continue
        if not resolved:
            findings.append({
                "unit_id": entry.get("unit_id"),
                "evidence_type": evidence_type,
                "evidence_ref": evidence_ref,
                "reason": "cited evidence does not resolve against real product-repo/registry/docs data",
            })
    return findings


def check_content_unit_merged_into_target_section(
    readme_text: str, dispositions: list[dict]
) -> list[dict]:
    """Hard gate. For every `merged_verbatim`/`merged_reframed` disposition, confirms the cited
    `target_section` was genuinely touched with something traceable to THIS unit -- at least one
    of its `salient_tokens` appears (case-insensitive) in that section's real body (via
    `_split_into_sections`; `target_section` of `"Intro"` or `"Project History"` (2026-08-10,
    MT031) both map to the `"__preamble__"` key, since the optional H3 `### Project History`
    section sits before the first `##` heading, alongside the unheaded Intro paragraph). This
    is the actual "reuse, not just presence-check" enforcement -- it cannot verify faithfulness
    of a reframe, only that the section was not silently left untouched while claiming a merge
    happened.

    A unit with zero extracted `salient_tokens` (plain narrative prose with no backtick/CamelCase/
    version/quoted identifiers -- common for a `redundant_with_existing` claim, since the whole
    point of "redundant" is that the SAME fact is phrased differently in two places) falls back to
    significant-word overlap: at least half of the excerpt's 4+-letter words (case-insensitive,
    reusing `check_section_job_distinctness`'s own established word-set-overlap idiom) must appear
    in the target section's body. Broadened from an earlier leading-20-char literal substring
    fallback (found live 2026-08-09, real portfolio data across all 5 MT030 Phase 1 pilot
    products): a literal substring almost never survives genuine rephrasing, so that fallback
    false-positived on dozens of real, individually source-verified redundant claims whose target
    section legitimately uses different wording for the same fact -- confirmed by manually
    re-reading a sample of the flagged entries against their real target sections before
    broadening this, not assumed.

    ALSO verifies an `excluded`/`redundant_with_existing` entry whose `verification.evidence_
    type == "candidate_section_reference"` -- the section named in `verification.evidence_ref`
    (not `target_section`, which is null for excluded entries) must genuinely contain the unit's
    trace, same token/word-overlap logic as a merge. Real, confirmed gap (found live 2026-08-09,
    MT030 Phase 1, independently by 2 of 5 pilot agents on words/net and slides/java):
    `check_content_unit_evidence_resolves` intentionally treats `candidate_section_reference` as
    always-resolved, deferring the real check to THIS function -- but this function originally
    only ever looked at `merged_*` dispositions, so a `redundant_with_existing` claim's cited
    section was never actually checked by either function. A lazy or wrong "already covered in
    section X" claim on an excluded entry would previously pass every hard gate undetected.
    """
    sections = _split_into_sections(readme_text)
    findings: list[dict] = []
    for entry in dispositions:
        disposition = entry.get("disposition")
        verification = entry.get("verification") or {}
        if disposition in ("merged_verbatim", "merged_reframed"):
            target = entry.get("target_section")
        elif disposition == "excluded" and verification.get("evidence_type") == "candidate_section_reference":
            target = verification.get("evidence_ref")
        else:
            continue
        section_key = "__preamble__" if target in ("Intro", "Project History") else target
        body = sections.get(section_key, "")
        tokens = entry.get("salient_tokens") or []
        if tokens:
            if not any(tok.lower() in body.lower() for tok in tokens):
                findings.append({
                    "unit_id": entry.get("unit_id"),
                    "target_section": target,
                    "reason": "none of this unit's salient tokens were found in the "
                              f"'{target}' section -- the merge/redundancy claim is not "
                              "traceable to real text",
                })
        else:
            excerpt_words = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", entry.get("excerpt") or "")}
            body_words = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", body)}
            overlap = excerpt_words & body_words
            if excerpt_words and len(overlap) / len(excerpt_words) < 0.5:
                findings.append({
                    "unit_id": entry.get("unit_id"),
                    "target_section": target,
                    "reason": "no salient tokens available, and fewer than half of the unit's "
                              f"significant words were found in the '{target}' section either",
                })
    return findings


def check_content_unit_no_exact_duplicate_merge(dispositions: list[dict]) -> list[dict]:
    """Hard gate. Flags two-plus disposition entries with an identical normalized `excerpt`
    merged into the identical `target_section` -- unambiguous, mechanically decidable
    duplication (the fuzzy near-duplicate case is `check_content_unit_probable_duplicate`'s
    heuristic below, not this hard gate).
    """
    seen: dict[tuple[str, "str | None"], list] = {}
    for entry in dispositions:
        if entry.get("disposition") not in ("merged_verbatim", "merged_reframed"):
            continue
        key = (
            re.sub(r"\s+", " ", (entry.get("excerpt") or "").strip().lower()),
            entry.get("target_section"),
        )
        seen.setdefault(key, []).append(entry.get("unit_id"))
    findings: list[dict] = []
    for (_excerpt, target), unit_ids in seen.items():
        if len(unit_ids) > 1:
            findings.append({
                "unit_ids": unit_ids,
                "target_section": target,
                "reason": "identical excerpt merged into the same section under multiple "
                          "unit_ids -- exact duplicate",
            })
    return findings


def check_content_unit_classification_plausibility(
    content_units: list[dict], dispositions: list[dict]
) -> list[dict]:
    """Heuristic, non-blocking. Cross-references each unit's mechanical `likely_category_1_
    prefilter` (emoji/CTA-phrase/exclamation signal) against the agent's own stated
    `classification`; a mismatch in either direction is a judgment prompt, never an automatic
    fail -- the prefilter is a cheap, disclosed-incomplete tone signal (see
    `_likely_category_1_signal`'s own docstring), not a reliable classifier on its own.
    """
    prefilter_by_id = {u["unit_id"]: u.get("likely_category_1_prefilter", False) for u in content_units}
    findings: list[dict] = []
    for entry in dispositions:
        uid = entry.get("unit_id")
        classification = entry.get("classification")
        if uid not in prefilter_by_id or classification not in _CONTENT_UNIT_CLASSIFICATIONS:
            continue
        prefilter = prefilter_by_id[uid]
        if prefilter and classification != "1_narrative_cta":
            findings.append({
                "unit_id": uid,
                "reason": f"prefilter suggests narrative/CTA tone but classified as {classification!r} "
                          "-- confirm this is a genuine checkable fact, not tone-driven prose",
            })
        elif not prefilter and classification == "1_narrative_cta":
            findings.append({
                "unit_id": uid,
                "reason": "classified as narrative/CTA but the prefilter found no tone signal -- "
                          "confirm this genuinely has nothing checkable/reusable in it",
            })
    return findings


def check_content_unit_probable_duplicate(dispositions: list[dict]) -> list[dict]:
    """Heuristic, non-blocking. Flags entry pairs sharing 2+ `salient_tokens` and the same
    `target_section` but a DIFFERENT `excerpt` -- likely-but-not-certain restatement of the same
    fact in two disposition entries (the exact-match case is
    `check_content_unit_no_exact_duplicate_merge`'s hard gate instead).
    """
    merged = [e for e in dispositions if e.get("disposition") in ("merged_verbatim", "merged_reframed")]
    findings: list[dict] = []
    for i, entry_a in enumerate(merged):
        for entry_b in merged[i + 1:]:
            if entry_a.get("target_section") != entry_b.get("target_section"):
                continue
            excerpt_a = (entry_a.get("excerpt") or "").strip().lower()
            excerpt_b = (entry_b.get("excerpt") or "").strip().lower()
            if excerpt_a == excerpt_b:
                continue  # exact duplicates are check_content_unit_no_exact_duplicate_merge's job
            tokens_a = {t.lower() for t in (entry_a.get("salient_tokens") or [])}
            tokens_b = {t.lower() for t in (entry_b.get("salient_tokens") or [])}
            shared = tokens_a & tokens_b
            if len(shared) >= 2:
                findings.append({
                    "unit_ids": [entry_a.get("unit_id"), entry_b.get("unit_id")],
                    "target_section": entry_a.get("target_section"),
                    "shared_tokens": sorted(shared),
                    "reason": "two different content units share 2+ salient tokens merged into "
                              "the same section -- likely restating the same fact twice",
                })
    return findings


_EMBEDDED_ACTIONABLE_SIGNAL_RE = re.compile(
    r"\bopen an issue\b|\bfile a request\b|\bcontact us\b|\bif you need\b|\blet us know\b"
    r"|\breach out\b|\bsubmit a request\b|\bget in touch\b",
    re.IGNORECASE,
)


def check_content_unit_embedded_actionable_fact(
    content_units: list[dict], dispositions: list[dict]
) -> list[dict]:
    """Heuristic, non-blocking (2026-08-10, MT031/Sixteenth incident). Flags a disposition whose
    `classification == "1_narrative_cta"` and `disposition == "excluded"` but whose own excerpt
    contains a signal phrase suggesting an embedded, independently-actionable pointer -- a real
    request/contact process bundled inside otherwise-pure narrative/CTA prose (the exact
    words/net u0021 shape: "...not the final shape of the project... [open an issue](../../
    issues) and tell us about your use case..." mixes a genuine hedge with a real, checkable
    fact about how the project handles scope-expansion requests).

    A hit is a prompt to re-examine the unit for a corrected classification carrying the real
    fact into a merge -- never an automatic fail; a unit already correctly split into a
    checkable-fact entry (classification 2/3/4, merged) plus a separate pure-hedge entry
    (classification 1, excluded) produces no finding, since only whole EXCLUDED category-1
    entries are examined here. Validated directly against all 5 MT030 Phase 1 pilot products'
    real, current content-dispositions.json: fires exactly once (the original, pre-fix u0021)
    and zero times elsewhere -- real precision on the one known positive case, no observed false
    positives on real data. Honest recall, not claimed complete: a differently-worded embedded
    fact ("we'd consider adding this on request") won't trip this fixed phrase list, the same
    disclosed limitation `check_process_narration_smells` already carries for its own list.
    """
    units_by_id = {u["unit_id"]: u for u in content_units}
    findings: list[dict] = []
    for entry in dispositions:
        if entry.get("classification") != "1_narrative_cta" or entry.get("disposition") != "excluded":
            continue
        uid = entry.get("unit_id")
        excerpt = (units_by_id.get(uid) or {}).get("excerpt") or entry.get("excerpt") or ""
        match = _EMBEDDED_ACTIONABLE_SIGNAL_RE.search(excerpt)
        if match:
            findings.append({
                "unit_id": uid,
                "signal_phrase": match.group(0),
                "reason": "excluded as pure narrative/CTA, but the excerpt contains an "
                          "actionable-sounding phrase -- re-examine for a real, distinct "
                          "checkable fact worth reclassifying and merging",
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
