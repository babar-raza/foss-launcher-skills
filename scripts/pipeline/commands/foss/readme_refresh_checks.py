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
import hashlib
import json
import re
import sys
from pathlib import Path

from lib.api_table_dupes import find_duplicate_rows as _find_duplicate_rows
from dataclasses import dataclass, field

# readme-refresh-seo-deps-headings-hardening mission (2026-08-19), TC-SDH-05: a monotonic
# version marker for this module, bumped every time a check_* function is added or a hard gate's
# pass/fail semantics change. Root-cause fix for a real structural gap: a candidate's
# "audit_portfolio -> clean: true" result is only ever true against the checks that existed AT
# THAT MOMENT -- nothing in this pipeline previously flagged that a "clean" candidate's
# certification had gone stale relative to checks added since. `_write_candidate_verification_
# marker` (readme_refresh_run.py) stamps this value into each candidate's own last-verified.json
# every time verification runs; `_checks_currency_findings` (same module) compares the stored
# value against this live constant and reports an advisory (never hard-gate) finding when they
# diverge -- the same mechanism class as `published_readme_current`'s republication-staleness
# tripwire, applied to this pipeline's OWN check coverage instead of the target repo's upstream
# state. Bump this by 1 whenever new check_* functions land (do not renumber retroactively).
CHECKS_MODULE_VERSION = 2  # 1 = snapshot at MT056 (2026-08-18); 2 = this mission's 3 new checks

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


_DIAGRAM_LABEL_MAX_TOKEN_CHARS = 28


def check_diagram_label_token_length(
    markdown_text: str, max_token_chars: int = _DIAGRAM_LABEL_MAX_TOKEN_CHARS
) -> list[dict]:
    """Heuristic (2026-08-14, MT040/Thirtieth incident). Flags any single space-delimited
    token inside a diagram node label or container title longer than `max_token_chars`.

    Real, upstream `mermaid.js` node labels wrap via a `foreignObject`/`white-space:
    break-spaces` div at a roughly-200px-wide budget -- `break-spaces` only breaks at literal
    whitespace, never mid-word (confirmed via a real, open, unfixed upstream defect,
    mermaid-js/mermaid#6424 "Long Words are Cut Off"), so a single unbroken token wide enough
    can overflow its node's rectangle regardless of the rest of the label wrapping normally.

    Not the root cause of the two real, live clipping defects this incident actually found and
    fixed (both traced to the retired per-node-wired diagram topology, not label length -- see
    the Thirtieth incident write-up) -- this check exists purely to guard against a second,
    independent, currently-latent failure class for FUTURE diagram content. The default ceiling
    (28) is deliberately set with headroom above the two longest real tokens already confirmed,
    by direct rendering, to be safe in this exact corpus and font (`DefinedNameCollection`, 21
    chars; `TextFragmentAbsorber`, 20 chars) -- a considered approximation, not a value derived
    from real font-metric measurement, which this module has no reliable way to perform.

    Heuristic, not a hard gate: the real safe ceiling depends on font metrics and the specific
    word's own glyph widths (a long word full of narrow characters like "iiiiiiiiiiiiiiiiiiii"
    fits where an equally-long word full of wide characters might not) -- a token-length count
    is a real, useful risk signal, never a certain verdict either way.
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []
    graph = parse_diagram(mermaid_text)
    findings: list[dict] = []

    labels: list[tuple[str, str]] = [
        (node_id, label) for node_id, label in graph.node_label.items()
    ]
    for line in mermaid_text.splitlines():
        title_match = _SUBGRAPH_START_RE.match(line.strip())
        if title_match and title_match.group(2):
            labels.append((title_match.group(1), title_match.group(2)))

    for label_id, label in labels:
        for token in label.split():
            stripped = token.strip(".,;:()[]{}\"'")
            if len(stripped) > max_token_chars:
                findings.append({
                    "node_id": label_id,
                    "label": label,
                    "token": stripped,
                    "token_length": len(stripped),
                    "reason": f"token {stripped!r} ({len(stripped)} chars) exceeds the "
                              f"{max_token_chars}-char safe-wrap ceiling and risks overflowing "
                              "its node on renderers that cannot break mid-word",
                })
    return findings


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
    "Dependencies",
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


# MT043 (TC-HARDEN-62, Thirty-Third incident, 2026-08-14): a small, explicit, disclosed-
# incomplete slug -> real display-name lookup, used to detect whether the anchor TEXT names a
# platform at all (family case) or names the CORRECT one (platform case). This is the table
# `readme_refresh_run.py`'s own `_classify_enterprise_relationship` imports (as `checks.
# _PLATFORM_DISPLAY_NAMES`) to compute the resolved link's own `public_platform` field -- one
# real table, two consumers, not two independent tables with an "accepted overlap cost" the way
# the pre-MT044 design had it (that duplication is gone now that `bridge_language` no longer
# exists as a concept at all -- see the Thirty-Fourth incident for the full correction).
_PLATFORM_DISPLAY_NAMES: dict[str, str] = {
    "net": ".NET", "java": "Java", "cpp": "C++", "python": "Python", "nodejs": "Node.js",
    "typescript": "TypeScript", "go": "Go", "rust": "Rust", "php": "PHP", "ruby": "Ruby",
    "android": "Android",
}
_PLATFORM_DISPLAY_NAME_RE = re.compile(
    r"\.NET\b|\bJava\b|C\+\+|\bPython\b|Node\.js|\bTypeScript\b|\bGo\b|\bRust\b|\bPHP\b|\bRuby\b|\bAndroid\b"
)
# MT044 (Thirty-Fourth incident, 2026-08-14): CORRECTED -- under MT043's original, now-reversed
# design, this pattern was REQUIRED to appear near a bridge link (a "prove you disclosed the
# implementation bridge" gate). That was the exact policy defect the mission exists to fix: the
# public anchor and surrounding prose must NEVER expose implementation-bridge reasoning, so this
# pattern is now used by `check_no_implementation_bridge_disclosure` to FORBID exactly this kind
# of sentence anywhere in the document, not to mandate it near one link. Kept as its own named
# constant (not folded into `_PROCESS_NARRATION_PATTERNS`) since its job -- implementation-bridge
# exposure -- is a distinct concern from process/audit-trail narration, even though both are
# "internal reasoning that must never reach a public README."
# Note: `(?!\w)` is used instead of a trailing `\b` after any alternative ending in `+` (C\+\+) --
# `\b` never matches between two non-word characters (a literal "+" and the space/punctuation that
# follows it), so a plain `\b` there would silently never fire for the C++ case. `(?!\w)` correctly
# requires "not immediately followed by a word character" regardless of what kind of character
# precedes it.
_IMPLEMENTATION_BRIDGE_DISCLOSURE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\bvia\s+(?:\.NET|Java|C\+\+|Node\.js|Python|Go|Rust)(?!\w)", re.IGNORECASE),
    re.compile(r"\bimplemented\s+(?:through|via)\b", re.IGNORECASE),
    re.compile(r"\bbacked\s+by\s+(?:\.NET|Java|C\+\+)(?!\w)", re.IGNORECASE),
    re.compile(r"\ba\s+wrapper\s+around\b", re.IGNORECASE),
    re.compile(r"\ba\s+binding\s+to\b", re.IGNORECASE),
    re.compile(r"\brather\s+than\s+as\s+an?\s+native\b", re.IGNORECASE),
)


def check_enterprise_edition_anchor_matches_relationship(
    readme_text: str, enterprise_link: "dict | None"
) -> list[dict]:
    """Hard gate (TC-HARDEN-62, MT043, Thirty-Third incident, 2026-08-14) -- CORRECTED 2026-08-14
    (MT044, Thirty-Fourth incident). `check_enterprise_edition_naming` (above) verifies the anchor
    says "Enterprise Edition" plus explains broader functionality; `check_enterprise_edition_
    link_resolves` (above) verifies the href matches the one real, verified target. NEITHER ever
    verified that the anchor's own PLATFORM CLAIM matches what the resolved destination actually
    represents -- confirmed live: `cells/typescript`'s candidate said "Aspose.Cells for .NET"
    while linking to the family-level `cells/` page, and both existing checks passed cleanly.

    `enterprise_link` is the factpack's own `{"url", "relationship", "public_platform", ...}`
    (`_detect_enterprise_link` + `_classify_enterprise_relationship`, `readme_refresh_run.py`) --
    this function compares the CANDIDATE's real anchor text against that real, computed
    relationship, per the plan's own CORRECTED Stage 3/4 anchor-text contract (MT044):

    - `"family"`: the anchor text itself must name NO platform at all -- scanned narrowly, just
      the bracketed anchor phrase, never the surrounding prose (deliberately avoids the `\\bGo\\b`-
      in-ordinary-English false-positive risk a paragraph-wide scan would carry).
    - `"platform"` (unified 2026-08-14, MT044 -- collapses the old, now-reversed `"exact"`/
      `"bridge"` split): the anchor must name the one real, normalized `public_platform`, and no
      other platform -- and MUST NOT carry any implementation-bridge qualifier (that prohibition
      is enforced portfolio-wide by the separate `check_no_implementation_bridge_disclosure` hard
      gate below, not duplicated here). Whether the underlying URL segment was a bare slug or a
      compound bridge slug is never distinguished at this layer -- the anchor is identical either
      way, by design.
    - `"unresolved"` or `None` (no relationship could be classified, or no verified target exists
      at all): no `products.aspose.com` link should appear in the candidate -- omit rather than
      guess, matching this skill's own "never invent a link not backed by verified data" rule.

    Findings carry a `reason` distinguishing each failure shape, never a bare "this failed".
    """
    findings: list[dict] = []
    relationship = (enterprise_link or {}).get("relationship")
    for match in _MD_LINK_RE.finditer(readme_text):
        anchor_text, href = match.group(1), match.group(2)
        if not _ENTERPRISE_LINK_HOST_RE.search(href):
            continue

        if relationship in (None, "unresolved"):
            findings.append({
                "anchor_text": anchor_text, "href": href, "reason": "no_classifiable_relationship",
                "detail": "no verified relationship (family/platform) could be established "
                          "between this product and the linked page -- the link should be "
                          "omitted rather than guessed",
            })
            continue

        if relationship == "family":
            if _PLATFORM_DISPLAY_NAME_RE.search(anchor_text):
                findings.append({
                    "anchor_text": anchor_text, "href": href, "reason": "platform_claim_on_family_link",
                    "detail": "the resolved destination is a family-level page (no single "
                              "platform), but the anchor text names a specific platform",
                })
            continue

        if relationship == "platform":
            expected_name = (enterprise_link or {}).get("public_platform") or ""
            names_found = set(_PLATFORM_DISPLAY_NAME_RE.findall(anchor_text))
            if expected_name and expected_name not in anchor_text:
                findings.append({
                    "anchor_text": anchor_text, "href": href, "reason": "missing_platform_name",
                    "detail": f"the resolved destination is the real {expected_name} edition, "
                              f"but the anchor text does not name it",
                })
            wrong_names = names_found - ({expected_name} if expected_name else set())
            if wrong_names:
                findings.append({
                    "anchor_text": anchor_text, "href": href, "reason": "wrong_platform_name",
                    "detail": f"anchor names {sorted(wrong_names)}, but the real destination is "
                              f"{expected_name!r}",
                })
            continue

    return findings


def check_no_implementation_bridge_disclosure(readme_text: str) -> list[dict]:
    """Hard gate (TC-HARDEN-62 REPLACEMENT, MT044, Thirty-Fourth incident, 2026-08-14). MT043's
    own bridge-relationship anchor contract MANDATED sentences of exactly this shape ("...via
    Java", "...implemented through .NET") near a bridge Enterprise link -- the precise policy
    defect this mission reverses. This is the portfolio-wide, document-wide replacement: no
    generated README may EVER expose how one platform is implemented through another, anywhere
    in the document (anchors, prose, tables, notes, comparison sections, badges, installation
    text, architecture descriptions, related-product descriptions, footnotes, generated
    metadata) -- not merely near an Enterprise Edition link, per the mission's own explicit
    "applies everywhere" requirement.

    Fenced code blocks are stripped first (matching this module's own established `check_
    process_narration_smells`/leak-scan convention) so a real code identifier -- e.g. a class
    literally named `JavaBridge` -- can never false-positive.

    Disclosed limitation, stated the same way every other fixed-phrase-list check in this module
    discloses it: a differently-worded implementation disclosure not matching one of these named
    patterns would still pass. The primary defense is the corrected composition contract (the
    anchor rule above, and the skill doc's own composition guidance) never producing this text in
    the first place -- this hard gate is the mechanical backstop, not the sole line of defense.
    """
    findings: list[dict] = []
    stripped = _ANY_FENCED_CODE_RE.sub("", readme_text)
    for pattern in _IMPLEMENTATION_BRIDGE_DISCLOSURE_PATTERNS:
        for match in pattern.finditer(stripped):
            start = max(0, match.start() - 60)
            end = min(len(stripped), match.end() + 60)
            findings.append({
                "matched_text": match.group(0),
                "context": stripped[start:end].replace("\n", " "),
                "reason": "implementation_bridge_disclosure",
                "detail": "generated READMEs must never expose how one platform is implemented "
                          "through another -- this phrase discloses an internal implementation-"
                          "bridge detail that must stay internal-only",
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
    # 2026-08-14 (MT039, Twenty-Ninth incident): widened from "repository" alone after a
    # confirmed synonym-evasion instance (slides/net: "the upstream project's own usage
    # examples") used the identical narration shape with a different noun.
    r"\bthe upstream (?:repository|project|readme)'?s own\b",
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
    # 2026-08-13: cells/cpp's real Development and Testing section disclosed a comparison
    # finding produced by this pipeline's own investigation -- that a nested doc's stated
    # commands don't match the real repo layout -- as generalized prose, with the
    # `upstream-issues.md` citation stripped out but the finding itself still narrated
    # ("does not match a plain clone of this repository"). Defense-in-depth alongside the
    # `_INTERNAL_LABEL_PATTERNS` filename block: excluding the filename while keeping the
    # finding is still a leak (per this incident's own governing policy).
    r"\bdoes not match a plain clone\b",
    # 2026-08-14 (MT039, Twenty-Ninth incident): a fifth, previously unnamed narration
    # category -- GENERATION-MECHANISM narration (describing HOW/WHY this document's own
    # section was composed, vs. WHAT the product does). Confirmed live across 9 products, all
    # variants of "[the table(s)/index/section below/above] mirrors/is organized as
    # [reference.aspose.org's own | its own | the same] [structure]" -- 4 of 10 confirmed
    # instances never name reference.aspose.org literally (paraphrased as "the library's
    # reference index", "the full, module-grouped reference", "the same data"), so this
    # targets the STRUCTURAL SHAPE, not a domain-name match. Individually verified against
    # every real, legitimate "mirror(s)/mirroring" use already in the portfolio
    # (MirroredProfile, "mirroring the WHATWG window.customElements API", "mirrors
    # OperatorCollection", "mirroring PDF 32000 names", "the API shape mirrors Aspose.PDF for
    # .NET", a CI-mirroring build instruction) -- zero of those share this pattern's subject
    # shape (a table/index/section noun as the thing doing the mirroring).
    r"\b(?:table|tables|index|section)\b[^.]{0,30}\b(?:below|above)\b[^.]{0,60}\bmirror(?:s|ing)?\b",
    r"\bgrouped\s+exactly\s+as\b",
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


# --- MT057 (Fifty-Seventh incident, 2026-08-19): upstream-issue GitHub Issue draft leak/
# rejection checks (TC-UIW-06/07). Deliberately a SEPARATE pattern list from
# _PROCESS_NARRATION_PATTERNS above, not an extension of it -- confirmed, before writing this,
# that several of the mission's own suggested additive patterns (most notably
# "upstream-issues.md") are ALREADY a legitimate, sanctioned citation in real, currently-passing
# README content (e.g. html/python's own "see upstream-issues.md for the root cause" pointer
# sentence, the exact pattern check_no_upstream_issue_leaked_into_readme's own docstring names
# as the correct, non-forensic remediation shape). Mutating the shared _PROCESS_NARRATION_
# PATTERNS list to add issue-draft-only rules would have silently broken every one of those
# already-correct README candidates the next time check_process_narration_smells runs against
# them -- a real regression this plan's own "verify against real content before trusting a
# pattern addition" discipline exists to catch. A citation of upstream-issues.md IS a real leak
# risk specifically inside a public GitHub Issue draft (it references this project's own
# internal tracking file, which does not exist in the target repo and reveals this pipeline's
# own tooling) even though it is fine inside this project's own generated README dev-docs -- two
# genuinely different contexts, two genuinely different pattern sets, reusing the SAME proven
# regex-based mechanism (never reimplemented) but never sharing the same constant.
_ISSUE_DRAFT_ADDITIONAL_LEAK_PATTERNS = [
    r"\btaskcard\b",
    r"\bMT0\d+\b",
    r"\bTC-[A-Z]+-\d+\b",
    r"\bcandidate-generation\b",
    r"\bsession_id\b",
    r"\bfinding_id\b",
    r"\bbundle_id\b",
    r"\bclone_cache\b",
    r"\bupstream-issues\.md\b",
    r"\bcontent-dispositions\.json\b",
    r"\breports[/\\]_scratch\b",
    r"\breports[/\\]repo-presenter\b",
    r"\breadme_refresh_(?:run|checks)\.py\b",
    r"C:\\Users\\|/home/[a-z]+/|/Users/[a-z]+/",
]
_ISSUE_DRAFT_ADDITIONAL_LEAK_RE = re.compile("|".join(_ISSUE_DRAFT_ADDITIONAL_LEAK_PATTERNS), re.IGNORECASE)


def check_no_internal_details_leaked_into_issue_draft(draft_text: str) -> list[dict]:
    """HARD GATE (MT057, TC-UIW-06). Reuses `_PROCESS_NARRATION_RE` verbatim (the same
    generation/verification-process narration language this module already forbids in public
    README prose is equally out of place in a public GitHub Issue draft -- an issue should state
    a plain, reproducible defect, never narrate this pipeline's own audit trail) PLUS the
    issue-draft-specific `_ISSUE_DRAFT_ADDITIONAL_LEAK_RE` above (internal task/file/path
    references that have no legitimate reason to ever appear in a public issue, unlike in this
    project's own generated README content). A whole-text scan (mirroring `check_process_
    narration_smells`'s own approach, not `check_no_upstream_issue_leaked_into_readme`'s
    per-scan-unit splitting) is correct here: a plain phrase/token match, unlike fingerprint-
    token-overlap matching, cannot misattribute a match across unrelated bullets -- the match
    position IS the leak's real location, so no unit-splitting is needed to avoid false
    cross-attribution.
    """
    findings = []
    for pattern_re, category in (
        (_PROCESS_NARRATION_RE, "process_narration"),
        (_ISSUE_DRAFT_ADDITIONAL_LEAK_RE, "internal_reference"),
    ):
        for match in pattern_re.finditer(draft_text):
            start = max(0, match.start() - 40)
            end = min(len(draft_text), match.end() + 40)
            findings.append({
                "phrase": match.group(0), "category": category,
                "context": draft_text[start:end].replace("\n", " "),
            })
    return findings


# --- MT057 (Fifty-Seventh incident, 2026-08-19): Stage-8 rejection-list check (TC-UIW-07).
# Genuinely new infrastructure -- confirmed by direct grep, no existing secret/credential
# pattern library exists anywhere in this repo before this addition. Two tiers, per this
# module's own established hard-gate/heuristic discipline (e.g. the badge-floor/dependency-
# claim checks' own hard-gate-vs-heuristic history): a HARD-GATE tier for precise, low-false-
# positive tokens that block outright, and an ADVISORY-ONLY tier (accusatory language, generic
# high-entropy strings) that must never auto-block until proven precise at real-content scale --
# the same "don't trust an unproven heuristic as a hard gate" lesson this plan has re-learned
# repeatedly (e.g. TC-HARDEN-32's own hard-gate-to-heuristic downgrade).
_ISSUE_DRAFT_HARD_REJECT_PATTERNS = [
    (r"\bghp_[A-Za-z0-9]{36,}\b", "github_personal_access_token"),
    (r"\bgho_[A-Za-z0-9]{36,}\b", "github_oauth_token"),
    (r"\bAKIA[0-9A-Z]{16}\b", "aws_access_key_id"),
    (r"\bxox[bp]-[A-Za-z0-9-]{10,}\b", "slack_token"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "private_key_block"),
    (r"\bGH_TOKEN\s*=\s*\S+", "token_assignment"),
    (r"https?://[^:/\s]+:[^@/\s]+@", "credential_in_url"),
    (r"C:\\Users\\[A-Za-z0-9_.-]+", "windows_absolute_user_path"),
    (r"/home/[A-Za-z0-9_.-]+/", "unix_absolute_home_path"),
    (r"/Users/[A-Za-z0-9_.-]+/", "macos_absolute_home_path"),
    (r"d-users-prora-onedrive-documents-github-humble-tome", "plan_file_name"),
]
_ISSUE_DRAFT_ADVISORY_ACCUSATORY_PATTERNS = [
    r"\byou broke\b", r"\byour fault\b", r"\bsloppy\b", r"\bnegligent\b", r"\blazy\b",
    r"\bincompetent\b", r"\bshould have known\b", r"\binexcusable\b",
]


def check_issue_draft_rejection_list(draft_text: str) -> dict:
    """Two-tier Stage-8 validation (MT057, TC-UIW-07). Returns
    `{"hard_gate_findings": [...], "advisory_findings": [...]}` -- callers (`validate-draft`)
    must block on any non-empty `hard_gate_findings`, and surface `advisory_findings` for the
    mandatory independent-reviewer step, never auto-block on those alone (high-entropy-string
    and accusatory-language detection are both real false-positive risks unproven at scale)."""
    hard: list[dict] = []
    for pattern, label in _ISSUE_DRAFT_HARD_REJECT_PATTERNS:
        for match in re.finditer(pattern, draft_text):
            hard.append({"reason": label, "matched_text_redacted": f"[{label} redacted, {len(match.group(0))} chars]"})
    advisory: list[dict] = []
    accusatory_re = re.compile("|".join(_ISSUE_DRAFT_ADVISORY_ACCUSATORY_PATTERNS), re.IGNORECASE)
    for match in accusatory_re.finditer(draft_text):
        start = max(0, match.start() - 40)
        end = min(len(draft_text), match.end() + 40)
        advisory.append({
            "reason": "accusatory_language", "phrase": match.group(0),
            "context": draft_text[start:end].replace("\n", " "),
        })
    return {"hard_gate_findings": hard, "advisory_findings": advisory}
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

    MT042 (TC-HARDEN-59, Thirty-Second incident, 2026-08-14): also scans the CANDIDATE's badge
    row (independent of the `## Installation` section, and of whether that section exists at
    all) for a `package_version`-category badge, and verifies its claimed identity against the
    exact same `install_info["candidate"]` data -- extending this already-hardened check to a
    second real consumer rather than building a parallel mechanism from scratch, per this
    module's own established discipline ("does this improve results without weakening what
    already works"). Same case-insensitive comparison, same disclosed `data/package_registry.
    json`-reliability caveat above, so this stays folded into the same heuristic, not a new
    hard gate.

    Returns `{"reason", "expected"?}` findings -- a prompt for human/agent judgment (matching
    this module's other data-source-dependent heuristics, e.g. `check_diagram_format_
    completeness_hint`), never an automatic fail.
    """
    findings: list[dict] = []

    sections = _split_into_sections(readme_text)
    section_text = sections.get("Installation", "")
    fallback_required = install_info.get("fallback_text_required")

    if section_text and fallback_required is not None:
        if fallback_required:
            if not _UNPUBLISHED_PACKAGE_SIGNAL_RE.search(section_text):
                findings.append({
                    "reason": "Installation section does not disclose that no confirmed "
                              "published package exists yet for this product (data/"
                              "package_registry.json shows fallback_text_required=True) -- "
                              "confirm whether this is a real gap or the registry data itself "
                              "is stale before treating this as a content defect",
                })
        else:
            expected = _expected_package_identity(install_info)
            if expected and expected.lower() not in section_text.lower():
                findings.append({
                    "reason": f"Installation section does not name the real, confirmed "
                              f"published package identity '{expected}' (data/package_registry."
                              f"json, registry_type={install_info.get('registry_type')!r}) -- "
                              f"confirm whether this is a real gap or the registry data itself "
                              f"is stale before treating this as a content defect",
                    "expected": expected,
                })

    if fallback_required is False:
        expected = _expected_package_identity(install_info)
        if expected:
            for badge in extract_badges(readme_text):
                if classify_badge(badge)["category"] != "package_version":
                    continue
                haystack = f"{badge.get('alt_text', '')} {badge.get('image_url', '')} {badge.get('link_url', '')}"
                if expected.lower() not in haystack.lower():
                    findings.append({
                        "reason": f"a badge classified 'package_version' does not name the "
                                  f"real, confirmed published package identity '{expected}' "
                                  f"(data/package_registry.json, registry_type="
                                  f"{install_info.get('registry_type')!r}) -- confirm whether "
                                  f"this is a real gap or the registry data itself is stale "
                                  f"before treating this as a content defect",
                        "expected": expected, "unit_id": badge.get("unit_id"),
                    })
    return findings


def _expected_package_identity(install_info: dict) -> "str | None":
    """Shared by `check_installation_matches_package_registry`'s Installation-section scan and
    its badge-row scan (MT042) -- the one real package-identity-resolution rule, computed once."""
    candidate = install_info.get("candidate") or {}
    registry_type = install_info.get("registry_type")
    if registry_type == "maven":
        return candidate.get("artifact_id")
    if registry_type == "go_modules":
        return candidate.get("module_path")
    return candidate.get("name")


_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.MULTILINE)


_INTERNAL_LABEL_PATTERNS = [
    r"\bpreserved repository details\b",
    r"\bdropped claims?\b",
    r"\bcarried forward from (?:the )?old readme\b",
    r"\bverification status\b",
    r"\bdisposition\b",
    r"\bcandidate readme\b",
    r"\bthis readme(?:'s)? (?:generation|generated)\b",
    # 2026-08-13: found live on cells/cpp -- a Development and Testing sentence cited
    # `upstream-issues.md` by name for "the corrected commands used above", a real,
    # confirmed leak neither this list nor check_no_upstream_issue_leaked_into_readme's
    # fingerprint mechanism caught (the cited path was clone-cache-prefixed in
    # upstream-issues.md's own evidence but bare in the README, so token overlap fell one
    # short of the 2-token threshold). `upstream-issues.md`/`content-dispositions.json` are
    # this project's own internal, never-published tracking files -- named here directly as
    # an unconditional block, the same "source allowlist, explicit rejection of internal
    # evidence" mechanism this incident's own governing mission required. Internal pipeline
    # path markers (the read-only clone cache, the knowledge/ merged layer, this project's
    # own reports/ evidence tree) get the same treatment -- none of these will ever exist in
    # or be reachable from a published target repository, regardless of phrasing.
    r"\bupstream-issues\.md\b",
    r"\bcontent-dispositions\.json\b",
    r"\.clone_cache\b",
    r"\bknowledge/[\w-]+/[\w-]+/merged\b",
    r"\breports/repo-presenter\b",
    r"\breports/readme_refresh_runs\b",
    # 2026-08-13 (Twenty-Fourth mission, cells/go): the two new sibling disposition files get the
    # identical unconditional-hard-gate protection as content-dispositions.json/upstream-
    # issues.md above -- same reasoning, same mechanism, no new wiring needed beyond these lines.
    r"\bstructure-dispositions\.json\b",
    r"\bbadge-dispositions\.json\b",
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


# Twenty-Fifth mission (2026-08-13, cells/java): a code EXAMPLE's own import/using/namespace
# statement is a real, checkable claim -- "this class lives at this exact package path" -- that
# nothing in this module verified before. Found live, real: the upstream cells/java repo renamed
# its Java package from `com.aspose.cells_foss` to `org.aspose.cells_foss`; the candidate's 20
# `import com.aspose.cells_foss.X;` statements all silently referenced a package that no longer
# exists, and check_named_member_accuracy's own scope (the `` - `ClassName` `` bullet-list
# convention only) never looks inside a fenced code block at all, so this class of staleness had
# no check anywhere.
_JAVA_FENCED_BLOCK_RE = re.compile(r"```java\n(.*?)```", re.DOTALL)
_JAVA_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\.([A-Z]\w*)\s*;", re.MULTILINE)
_JAVA_PACKAGE_DECLARATION_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)


def check_code_example_imports_match_source(readme_text: str, clone_cache_root: str) -> list[dict]:
    """Hard gate. Verifies every Java `import <package>.<ClassName>;` statement inside a
    ```java fenced code block resolves to a real, currently-declared class at that exact
    package path in the clone cache -- catches a stale package/namespace rename between when
    a candidate was composed and when the clone cache (or the real upstream repo) was last
    refreshed. This is exactly as mechanically decidable as `check_license_link_target`/
    `check_api_reference_classes_exist_in_reference_site` -- a wrong import is a real,
    unambiguous compile failure, not a judgment call, so this is a hard gate.

    For each `(package, class)` pair found: locates real source file(s) declaring `class`
    via `_find_class_source_files` (the same grep-based scan `check_named_member_accuracy`
    already uses -- same file-discovery limitations apply, see that function's own docstring),
    then reads each candidate file's own real `package <name>;` declaration and compares it
    against the claimed package. Two distinct finding reasons: `class_not_found` (no source
    file anywhere declares this class at all) and `wrong_package` (the class is real, but every
    file declaring it uses a different package than the import statement claims -- the exact
    cells/java shape this check exists to catch). A class genuinely declared under two
    different real packages in different files (unusual, but not impossible) counts as a match
    if the claimed package is among the real ones -- this check flags a wrong claim, not merely
    an incomplete one.

    Scope, disclosed not hidden: Java only for this pass, matching the concrete, live-confirmed
    defect this check exists to catch and this plan's own established "prove one language first"
    rollout discipline (TC-HARDEN-01's own Python-first precedent for `verify_examples`).
    Extending to other languages' import/using/namespace conventions (Python, C#, Go, Rust,
    TypeScript, C++) is real, disclosed follow-up scope, never silently assumed covered here.

    JDK standard-library imports (`java.*`/`javax.*`) are skipped outright (2026-08-17, the
    slides/* portfolio audit) -- a real, confirmed false-positive class found live against
    `slides/java`'s own real candidate, which legitimately imports `java.time.LocalDateTime`,
    `java.nio.file.Path`, and `java.io.ByteArrayOutputStream` in its worked examples. The JDK's own
    standard-library classes are never declared anywhere in a product's clone cache (they ship
    with the JDK itself, not the product's own source), so this check's `class_not_found` path
    fired on every one of them -- 3 findings against a candidate with zero real import defects.
    Scoped narrowly to the two real JDK root package prefixes, which cannot collide with any real
    Aspose package name.
    """
    root = Path(clone_cache_root)
    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for block_match in _JAVA_FENCED_BLOCK_RE.finditer(readme_text):
        for import_match in _JAVA_IMPORT_RE.finditer(block_match.group(1)):
            claimed_package, class_name = import_match.group(1), import_match.group(2)
            if claimed_package == "java" or claimed_package.startswith("java.") or \
                    claimed_package == "javax" or claimed_package.startswith("javax."):
                continue
            key = (claimed_package, class_name)
            if key in seen:
                continue
            seen.add(key)
            source_files = _find_class_source_files(root, class_name)
            if not source_files:
                findings.append({
                    "package": claimed_package, "class_name": class_name,
                    "reason": "class_not_found",
                    "detail": f"`{claimed_package}.{class_name}` -- no source file anywhere in "
                              f"the clone cache declares a class named {class_name!r}",
                })
                continue
            real_packages: set[str] = set()
            for path in source_files:
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                pkg_match = _JAVA_PACKAGE_DECLARATION_RE.search(text)
                if pkg_match:
                    real_packages.add(pkg_match.group(1))
            if real_packages and claimed_package not in real_packages:
                findings.append({
                    "package": claimed_package, "class_name": class_name,
                    "reason": "wrong_package",
                    "detail": f"`import {claimed_package}.{class_name};` -- {class_name} is "
                              f"real, but its actual current package is "
                              f"{sorted(real_packages)!r}, not {claimed_package!r}",
                })
    return findings


# check_api_reference_intro_names_classes (2026-08-05) was RETIRED 2026-08-09 (MT027) --
# absorbed into check_api_reference_classes_exist_in_reference_site (below), which runs the
# same two bad-pattern checks PLUS real class-name verification against reference.aspose.org,
# and was elevated from heuristic to hard gate now that class-name verification makes the
# underlying question mechanically decidable. See that function's docstring for the full
# rationale. _API_REF_SECTION_RE (the intro-only section extractor) is kept -- still used there.
# Re-bound 2026-08-15 (MT045, Thirty-Fifth incident, TC-HARDEN-67): was `(?=<details>|\Z)`,
# which silently over-captures the ENTIRE remainder of the document as "the intro sentence
# region" whenever no `<details>` tag exists in the file at all -- confirmed live against
# barcode/python's real defective (uncollapsed) text, which captured all 5115 remaining
# characters. Re-bound to ALSO stop at the next `##` heading (whichever of `<details>`/next
# heading/EOF comes first) -- a strict superset of the old boundary, so a candidate that
# still has its `<details>` tag (the common, already-correct case) is completely unaffected
# (confirmed by the existing `test_check_api_reference_classes_flags_bare_wildcard` fixture,
# which has no other `##` heading and depends on the intro region stopping exactly at
# `<details>`, not at EOF); only the previously-unbounded no-`<details>`-anywhere case is
# newly, correctly bounded. Defensive: becomes structurally unreachable for a candidate that
# also passes `check_api_reference_detail_collapsed` (which requires a real `<details>` tag
# to exist), but guards a still-failing candidate mid-iteration.
_API_REF_SECTION_RE = re.compile(
    r"^##\s+API reference\s*$(.*?)(?=<details>|^##\s+|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
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


# ============================================================================================
# Thirty-Seventh incident / MT047 (2026-08-15): independent verification of the `font/python`
# preservation audit's Finding 1 (3 internal-tooling classes -- `TaskTokenEstimate`,
# `TaskCompletionReceipt`, `CompletedTaskRecord` -- leaked into the public API Reference table).
# `check_api_reference_classes_exist_in_reference_site` (above) and `check_api_reference_table_
# completeness` (below) both verify a cited class is REAL -- neither has any concept of whether
# a real class is genuinely PUBLIC. Confirmed live: `reporting.py`'s 3 classes are real (defined,
# not forward-declared), never imported by any other file under `src/aspose_font/`, and back
# their own separate `[project.scripts]` console entry (`aspose-font-reporting`) distinct from
# the product's real `aspose-font` entry -- an internal-tooling module, not part of the library's
# own public surface, that both existing checks correctly (and blindly) confirmed as "real."
#
# The precise, validated signal (Stage 1's own 5-control-pair test): internal FAN-IN, not
# `__init__.py` absence alone. A naive "not in __init__.py's __all__" scan was tried first and
# rejected -- it produced 0 to 237 "not exported" classes across every real Python product in
# the portfolio, an unusable false-positive rate, since most legitimate deep API surface is
# reachable only via submodule import, never top-level re-export (the real `FontConverter`
# control case: absent from `__all__`, genuinely real, 6 real internal importers). Python-first
# for this pass (TC-HARDEN-01's own established "prove one language first, disclose the rest as
# deferred" precedent) -- heuristic tier, not a hard gate, validated against exactly one
# product's 5 real control pairs so far (Stage 12's portfolio dry run is real, deterministic
# machinery verification, not a second-language precision proof).
# ============================================================================================

_INIT_ALL_RE = re.compile(r"__all__\s*=\s*\[(.*?)\]", re.DOTALL)
_INIT_QUOTED_NAME_RE = re.compile(r"[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']")
_INIT_IMPORT_LINE_RE = re.compile(r"^\s*from\s+\S+\s+import\s+(.+)$", re.MULTILINE)
_INIT_CLASS_DEF_RE = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


def _module_internal_fan_in(clone_cache_root: str, class_name: str) -> "int | None":
    """Counts distinct source files under `clone_cache_root` (Python-first: `*.py` only, a
    disclosed, deliberate scope narrowing -- see this section's own header comment) that
    reference `class_name` as plain text, EXCLUDING the file(s) that actually define it
    (`_find_class_source_files`, the same lookup `check_named_member_accuracy`/`check_api_
    reference_classes_exist_in_reference_site` already use -- no new class-location logic).
    `None` when unusable (no clone cache directory, or the class can't be located at all) --
    never a false negative masquerading as a real zero.

    A cheap whole-word text search, not a real import-graph parse (same "presence not proof"
    honesty this module already discloses for `check_named_member_accuracy`) -- a class name
    that happens to collide with an unrelated identifier in a docstring/comment elsewhere would
    inflate this count, which only makes the check that consumes this value MORE conservative
    (fewer false "internal-only" flags), never less.
    """
    root = Path(clone_cache_root)
    if not root.is_dir():
        return None
    defining_files = _find_class_source_files(root, class_name)
    if not defining_files:
        return None
    defining = {p.resolve() for p in defining_files}
    reference_re = re.compile(rf"\b{re.escape(class_name)}\b")
    skip_dirs = {".git", "node_modules", "__pycache__", "target", "build", "dist", "bin", "obj"}
    fan_in = 0
    for path in root.rglob("*.py"):
        if not path.is_file() or skip_dirs & set(path.parts):
            continue
        if path.resolve() in defining:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if reference_re.search(text):
            fan_in += 1
    return fan_in


def _class_has_exported_subclass_in_same_file(
    clone_cache_root: str, class_name: str, root_exports: "set[str] | None"
) -> bool:
    """MT048 (note/python pilot, 2026-08-15): a class can be genuinely PUBLIC by inheritance
    visibility even with zero cross-file fan-in and zero direct top-level export -- the common
    Python idiom of a base exception (or base class generally) that callers reach almost
    exclusively via its EXPORTED subclasses (`except BaseError:` catches every subclass without
    ever naming the base directly in most call sites), not via direct reference elsewhere in the
    source tree. Confirmed live and real: `note/python`'s `AsposeNoteError` (base of 5 real,
    all-exported exception subclasses defined in the same `exceptions.py`) has `_module_internal_
    fan_in == 0` and is absent from `_find_top_level_init_exports`' result -- the exact shape
    `check_api_reference_class_internal_only` (MT047/TC-HARDEN-76) was built to flag as a
    possible internal-tooling leak, but this is the OPPOSITE case: a real, upstream-confirmed
    (not fixable here) under-export of a genuinely public base class, already correctly disclosed
    in this candidate's own API Reference row and `upstream-issues.md`, not an internal-tooling
    class like `font/python`'s real `reporting.py` leak (which has no exported subclasses at all
    -- this distinguishing signal doesn't accidentally clear that real positive control).

    Cheap, disclosed heuristic (same "presence not proof" honesty as `_module_internal_fan_in`):
    scans the class's own defining file(s) for `class Sub(...ClassName...):` lines and returns
    True the moment any such subclass name is itself in `root_exports`. `False` -- never raises --
    when `root_exports` is falsy/None (nothing to confirm a subclass against) or the class has no
    locatable defining file.
    """
    if not root_exports:
        return False
    root = Path(clone_cache_root)
    defining_files = _find_class_source_files(root, class_name)
    if not defining_files:
        return False
    subclass_re = re.compile(
        rf"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\b{re.escape(class_name)}\b[^)]*\)",
        re.MULTILINE,
    )
    for path in defining_files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in subclass_re.finditer(text):
            if match.group(1) in root_exports:
                return True
    return False


def _find_top_level_init_exports(clone_cache_root: str) -> "set[str] | None":
    """Best-effort, disclosed-incomplete scan of a Python product's top-level `__init__.py`
    (`src/*/__init__.py`, PLUS `src/*/*/__init__.py`, falling back to `*/__init__.py` for a
    non-`src`-layout checkout) for names it makes available at the package's own top level: a
    literal `__all__` list, every name in a `from .module import X, Y as Z` statement, and every
    top-level `class X` defined directly inside `__init__.py` itself. `None` -- never an empty
    set -- when no `__init__.py` is discoverable at all (Stage 3's own confirmed real gap:
    `3d/python`, `cells/python`, `email/python`, `slides/python`, `words/python` have no
    discoverable top-level `__init__.py` under this convention) -- an empty set would be silently
    indistinguishable from "genuinely exports nothing," which is never true for a real, shipping
    product.

    MT048 (note/python pilot, 2026-08-15): a real, confirmed bug found live in this function's
    own first use against a second product. `note/python` ships a real, PEP 420-style two-level
    namespace layout -- `src/aspose/__init__.py` (a thin namespace stub, `__all__ = ["note"]`)
    plus the REAL package init one level deeper, `src/aspose/note/__init__.py` (the genuine
    33-class export list). The original one-level-only glob matched the stub and never even
    looked at the real file, so every class this function should have confirmed as exported came
    back as a false "internal-only" candidate -- confirmed directly: `_class_has_exported_
    subclass_in_same_file`'s own fix (above) was silently defeated by this bug in its first real
    test against `note/python`'s real clone cache, not a synthetic fixture. `src/*/*/__init__.py`
    is added as an ADDITIONAL source (unioned with the one-level glob, not a fallback) --
    deliberately not the ONLY pattern, since a genuinely flat `src/{package}/__init__.py` layout
    (e.g. `font/python`'s real `src/aspose_font/__init__.py`) needs the one-level match to keep
    working exactly as before. A two-level submodule init that isn't really a namespace-package
    root (e.g. a hypothetical `src/mypackage/utils/__init__.py`) can also match this new pattern
    and get its own local names folded into the same export set -- an accepted, disclosed
    imprecision: per this module's own established principle for `_module_internal_fan_in`, a
    stray extra name in `root_exports` only makes the heuristic that consumes this value MORE
    conservative (fewer false internal-only flags), never less.
    """
    root = Path(clone_cache_root)
    candidates = list(root.glob("src/*/__init__.py")) + list(root.glob("src/*/*/__init__.py"))
    if not candidates:
        candidates = list(root.glob("*/__init__.py"))
    if not candidates:
        return None
    exports: set[str] = set()
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        all_match = _INIT_ALL_RE.search(text)
        if all_match:
            exports.update(_INIT_QUOTED_NAME_RE.findall(all_match.group(1)))
        for import_line in _INIT_IMPORT_LINE_RE.findall(text):
            for name in import_line.split(","):
                name = name.strip().split(" as ")[-1].strip()
                if name:
                    exports.add(name)
        exports.update(_INIT_CLASS_DEF_RE.findall(text))
    return exports


def check_api_reference_class_internal_only(
    readme_text: str,
    reference_index: "dict[str, list[dict]] | None",
    clone_cache_root: "str | None",
    exclusions: "set[str] | None" = None,
    platform: "str | None" = None,
) -> list[dict]:
    """Heuristic, non-blocking (TC-HARDEN-76, MT047/Thirty-Seventh incident, 2026-08-15). For
    every class cited in the API Reference **table** (`_parse_readme_api_tables` -- the exact
    gap neither `check_api_reference_table_completeness` (mirror-fidelity only) nor `check_api_
    reference_classes_exist_in_reference_site` (the curated-bullet convention only, never the
    module table) covers), flags a class whose `_module_internal_fan_in` is exactly `0` AND
    which is absent from `_find_top_level_init_exports`' result, as a "possible internal-only
    class -- verify before shipping" prompt.

    Scope is deliberately narrowed to classes `reference_index` (`parse_reference_api_index`'s
    own output) already independently confirms as real -- fabricated-name detection is `check_
    api_reference_classes_exist_in_reference_site`'s job, not this one's; conflating the two
    would re-flag an already-caught fabrication under a confusing, unrelated reason string.
    Silently returns `[]` (never a false positive) when `clone_cache_root` is absent/unusable,
    when the API Reference section/table is empty, or when `reference_index` has nothing to
    confirm any cited class against.

    Heuristic tier, not a hard gate -- validated against exactly one product's 5 real control
    pairs at introduction (`reporting.py`'s 3 real leaked classes vs. `converter.py`/
    `FontConverter`, `_io.py`/`BinaryReader`, `eot/font.py`/`EotFont`, `web.py`/`WebFontAsset`).
    MT048 (note/python pilot, 2026-08-15) is this heuristic's first real run against a SECOND
    product's real content, per this incident's own explicit "not yet exercised against real
    content from any other product" disclosure -- and found a real, confirmed false-positive
    class: `note/python`'s `AsposeNoteError` (a genuinely public base exception, zero cross-file
    fan-in, absent from `__all__`, but the base of 5 real, all-exported subclasses defined in the
    same file) trips the original fan-in-only signal exactly like a real internal-tooling leak
    would. `_class_has_exported_subclass_in_same_file` (below) closes this specific, real,
    evidence-backed false-positive shape without weakening the original `reporting.py`-style
    positive control (which has no exported subclasses at all, so the new exemption never fires
    for it) -- portfolio-wide precision otherwise remains genuinely unproven beyond these two real
    products, per this plan's own "prove precision at scale before hardening" discipline (the
    TC-HARDEN-32 precedent).

    `exclusions` (added MT048): a second, real, confirmed defect found this same incident -- the
    finding's own `reason` text has ALWAYS told the reader to "record a confirmed internal class
    in data/api_reference_class_exclusions.json to suppress this prompt permanently," but this
    function never actually accepted or consulted that file (only `check_api_reference_table_
    completeness`'s unrelated `missing_class` requirement did) -- a real, live-confirmed case of a
    finding message promising a mechanism that did not exist. `exclusions` (a `set[str]` of class
    names, same shape `check_api_reference_table_completeness` already uses) now makes that
    promise true: a cited class present in `exclusions` is skipped before any fan-in/export check
    runs, exactly like the analogous mirror-fidelity gate already does.

    `platform` (added 2026-08-17, the slides/* portfolio audit): both `_module_internal_fan_in`
    and `_find_top_level_init_exports` are Python-specific concepts (a top-level package
    `__init__.py`'s own export list) with no equivalent detection for any other language this
    portfolio covers. Run for real against 3 non-Python products for the first time this incident
    (C++/`slides/cpp`, Java/`slides/java`, .NET/`slides/net`), this heuristic flagged 161, 238, and
    260+ classes respectively -- effectively every class in each table, since a non-Python
    product's real public API is (correctly) never present in a Python-shaped `__init__.py`
    export list, and cross-file `import`/`using`/`#include` fan-in was never implemented as a
    per-language check here at all. This is 100% noise, not signal, for those 3 languages -- every
    real internal-class-leak finding in that same audit (slides/cpp's ~30 `Internal::` namespace
    classes, slides/net's 21 `Internal/` classes) was found by direct, manual per-language
    convention inspection, never by this function. Scoped to a real no-op (empty findings) for any
    `platform != "python"` rather than continuing to emit unusable noise -- the same "Python-first,
    disclosed-deferred for other languages" posture already established for this exact function's
    own sibling helpers (TC-HARDEN-76), now made explicit and enforced here too, not merely implied
    by the docstring's own prior "portfolio-wide precision genuinely unproven beyond Python"
    disclosure. A real per-language extension (C++ `Internal`-namespace detection, Java
    package-private/`internal`-package detection, C# `internal`-keyword detection) remains a real,
    disclosed, un-built follow-on -- not attempted here, since each is a genuinely different
    detection mechanism, not a parameter tweak on this one.
    """
    if platform is not None and platform != "python":
        return []
    if not clone_cache_root or not Path(clone_cache_root).is_dir():
        return []
    section_match = _FULL_API_REF_SECTION_RE.search(readme_text)
    if not section_match:
        return []
    tables = _parse_readme_api_tables(section_match.group(1))
    cited_classes = {cls for classes in tables.values() for cls in classes}
    if not cited_classes:
        return []
    real_classes = {row["class"] for rows in (reference_index or {}).values() for row in rows}
    if not real_classes:
        return []
    root_exports = _find_top_level_init_exports(clone_cache_root)
    exclusions = exclusions or set()
    findings: list[dict] = []
    for cls in sorted(cited_classes):
        if cls not in real_classes:
            continue
        if cls in exclusions:
            continue
        fan_in = _module_internal_fan_in(clone_cache_root, cls)
        if fan_in != 0:
            continue
        if root_exports and cls in root_exports:
            continue
        if _class_has_exported_subclass_in_same_file(clone_cache_root, cls, root_exports):
            continue
        findings.append({
            "class_name": cls,
            "reason": f"'{cls}' has zero internal fan-in (no other real source file references "
                      "it) and is absent from the top-level package __init__.py exports -- "
                      "possible internal-only class; verify before shipping (record a confirmed "
                      "internal class in data/api_reference_class_exclusions.json to suppress "
                      "this prompt permanently, once genuinely confirmed)",
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
    exclusions: "set[str] | None" = None,
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

    `exclusions` (TC-HARDEN-77, MT047/Thirty-Seventh incident, 2026-08-15): an optional set of
    class names -- sourced from `data/api_reference_class_exclusions.json`, this product's own
    real, evidence-required entries -- removed from `reference_index`'s real classes BEFORE the
    mirror comparison runs. An excluded class is never required in the table (no `missing_class`
    for it, regardless of whether reference.aspose.org's own index still lists it) -- and if it
    is present in the table anyway, it now correctly surfaces as `unrecognized_class` (filtered
    out of the "real" side of the comparison), a real, mechanical deterrent against reintroducing
    a confirmed-internal class the table-composition step was told to leave out. `None`/empty
    (the default) preserves this function's exact prior behavior -- purely additive, no existing
    caller's result changes without opting in.
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
    exclusions = exclusions or set()
    real_modules = {
        module: {row["class"] for row in rows if row["class"] not in exclusions}
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


def check_diagram_container_duplicates_capability(markdown_text: str) -> list[dict]:
    """Heuristic (2026-08-13, cells/java healing pass). Flags a Starting-Points/Outputs node
    whose label strongly overlaps an existing Capabilities node's label -- the exact shape of
    two real, live defects found the same day: cells/java's Starting Points node "JPEG, PNG,
    GIF, or BMP image bytes (for embedded pictures)" duplicated its own Capabilities node
    "Embedded pictures"; its Outputs node "Load diagnostics and repair report" duplicated its
    own Capabilities node "Load diagnostics and repair reporting". Both facts were ALSO already
    correctly documented in Key Capabilities prose, so deleting the Starting-Points/Outputs
    node lost zero information -- a hit here usually means DELETE the flagged node, not
    strengthen its evidence (see skills/readme-refresh.md's diagram-composition guidance).

    Deliberately a heuristic, not a hard gate: word overlap is a proxy for "this is the same
    concept twice," not proof -- a Starting Points node legitimately shares a word with the
    Capability it feeds (e.g. "CSV files" naturally shares "CSV" with "CSV import and export"),
    and that is NOT a duplicate. To avoid firing on this common, legitimate pattern, a hit
    requires BOTH >= 2 shared significant words (>= 4 letters, minus `_GENERIC_LABEL_WORDS`)
    AND that shared count covers at least half of the SMALLER of the two label's own word sets
    (mirroring `check_content_unit_merged_into_target_section`'s own established "half the
    significant tokens" idiom) -- confirmed against the real cells/java pair (matches: 2-3
    shared words, >=50% coverage both cases) and a real negative control ("CSV files" / "CSV
    import and export": 1 shared word, correctly never reaches the >=2 floor).
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []
    graph = parse_diagram(mermaid_text)

    capability_nodes = [nid for nid, kind in graph.node_subgraph.items() if kind == "capabilities"]
    other_nodes = [nid for nid, kind in graph.node_subgraph.items() if kind in ("starting_points", "outputs")]

    findings = []
    for other_id in other_nodes:
        other_label = graph.node_label.get(other_id, "")
        other_words = {w.lower() for w in _WORD_RE.findall(other_label)} - _GENERIC_LABEL_WORDS
        if not other_words:
            continue
        for cap_id in capability_nodes:
            cap_label = graph.node_label.get(cap_id, "")
            cap_words = {w.lower() for w in _WORD_RE.findall(cap_label)} - _GENERIC_LABEL_WORDS
            if not cap_words:
                continue
            shared = other_words & cap_words
            if len(shared) < 2:
                continue
            smaller = min(len(other_words), len(cap_words))
            if len(shared) / smaller < 0.5:
                continue
            findings.append({
                "node_id": other_id, "label": other_label,
                "container": graph.node_subgraph[other_id],
                "capability_node_id": cap_id, "capability_label": cap_label,
                "shared_words": sorted(shared),
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


def check_api_reference_detail_collapsed(readme_text: str) -> list[dict]:
    """Hard gate (2026-08-15, MT045 / Thirty-Fifth incident, TC-HARDEN-67). Mirrors
    `check_examples_table_collapsed`'s design exactly, one section over: the
    `## API Reference` section's detail content -- every real `| Class | Description |`
    table row (the module-grouped table MT028 introduced) and every curated
    `` - `ClassName` `` member-detail bullet (the convention some products still carry) --
    must live INSIDE a `<details><summary>...</summary>...</details>` block, never fully
    expanded above the fold.

    The collapse decision is deterministic and size-independent -- confirmed via
    `tex/python`'s own 11-class table (the smallest real API surface in the 30-product
    portfolio), which still collapses; this is never a row-count threshold.

    Root cause this closes: unlike its sibling `check_examples_table_collapsed` (built one
    day after the `<details>` convention it enforces), no equivalent check ever existed for
    `## API Reference` -- the convention survived purely through composing-agent imitation
    of prior sibling candidates, which breaks the moment a clean-room/isolated composition
    pass runs with nothing to imitate from (confirmed live: `barcode/python`, `3d/net`, and
    `3d/typescript` all independently produced fully-expanded API Reference content across 2
    separate regeneration batches).

    Returns a list of {"reason": ...} findings; empty if the section has no detail content
    at all (an intro-sentence-only section is vacuously fine, same as `## Additional
    examples` when it has too few real snippets to justify collapsing), or every table row
    / member bullet found is genuinely inside a `<details>` block.
    """
    section_match = _FULL_API_REF_SECTION_RE.search(readme_text)
    if not section_match:
        return []
    section_text = section_match.group(1)

    detail_matches = list(_EXAMPLES_TABLE_RE.finditer(section_text)) + list(
        _CLASS_BULLET_RE.finditer(section_text)
    )
    if not detail_matches:
        return []

    details_blocks = list(_DETAILS_BLOCK_RE.finditer(section_text))

    def _inside_any_details_block(pos: int) -> bool:
        return any(block.start() <= pos < block.end() for block in details_blocks)

    for match in detail_matches:
        if not _inside_any_details_block(match.start()):
            return [{
                "reason": "the API Reference section's detail content (a table row and/or a "
                          "curated member bullet) is not inside a <details> block -- it must "
                          "be collapsed, never fully expanded above the fold, regardless of "
                          "row/class count",
            }]
    return []


_EXAMPLE_HEADING_LINE_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*$", re.MULTILINE)
_GENERIC_EXAMPLE_HEADING_RE = re.compile(r"^example\s*\d*$", re.IGNORECASE)


def check_additional_example_headings(readme_text: str) -> list[dict]:
    """Hard gate (readme-refresh-seo-deps-headings-hardening mission, 2026-08-19). Every worked
    example inside the "View Additional Examples" `<details>` disclosure must be introduced by
    its own real, non-generic, unique heading naming the actual developer task -- not a plain
    sentence directly followed by a code fence. Confirmed real, previously undocumented,
    portfolio-wide gap: no contract or validator for this existed anywhere in this pipeline
    before this mission (3d/net's own 5 collapsed examples, read verbatim, had zero heading
    markup of any kind -- not even a generic "Example N" label).

    Deliberately scoped to the `<details>` disclosure only, matching the reported defect and
    the skill's own illustrative contract shape (`<details><summary>View Additional
    Examples</summary>` -> `### heading` -> ... -> `### heading` -> ... -> `</details>`) -- the
    always-visible flagship example ahead of the disclosure is a different, already-established
    convention (one primary worked example, introduced by the section's own lead-in prose) and
    is not required to carry its own heading by this gate.

    A fenced code block appearing before any heading in the disclosure is a finding (no
    introducing heading at all). A heading that owns at least one fenced code block (its
    "territory", up to the next heading or the end of the disclosure) is checked for: a generic
    label ("Example", "Example 1", case-insensitive) -- finding; a heading text duplicated
    (case-insensitive) elsewhere in the same disclosure -- finding. A heading with no code block
    in its territory (a rare sub-grouping heading, not itself "an example") is not itself
    required to be non-generic/unique by this gate -- only headings that actually introduce a
    worked example are.

    Multiple code blocks legitimately sharing one heading (e.g. a "before" and "after" snippet
    under the same worked example) are correctly treated as ONE example, not flagged as a
    second, headingless one -- this is why the check walks heading "territories" rather than
    looking backward from each individual code block.
    """
    section_match = _EXAMPLES_SECTION_RE.search(readme_text)
    if not section_match:
        return []
    section_text = section_match.group(1)
    details_match = _DETAILS_BLOCK_RE.search(section_text)
    if not details_match:
        return []
    details_text = details_match.group(0)

    code_blocks = list(_ANY_FENCED_CODE_RE.finditer(details_text))
    if not code_blocks:
        return []

    headings = list(_EXAMPLE_HEADING_LINE_RE.finditer(details_text))
    findings: list[dict] = []

    first_heading_start = headings[0].start() if headings else len(details_text)
    for code_match in code_blocks:
        if code_match.start() < first_heading_start:
            findings.append({
                "reason": "a worked example (fenced code block) inside \"View Additional "
                          "Examples\" appears before any heading introduces it -- every "
                          "example must begin with a real, non-generic heading naming the "
                          "actual developer task",
                "context": details_text[max(0, code_match.start() - 80):code_match.start()]
                    .replace("\n", " ").strip()[-120:],
            })

    seen_heading_texts: dict[str, int] = {}
    for i, heading in enumerate(headings):
        heading_text = heading.group(2).strip()
        territory_end = headings[i + 1].start() if i + 1 < len(headings) else len(details_text)
        has_code = any(heading.end() <= cb.start() < territory_end for cb in code_blocks)
        if not has_code:
            continue
        if _GENERIC_EXAMPLE_HEADING_RE.match(heading_text):
            findings.append({
                "reason": f"heading {heading_text!r} is a generic label (\"Example\"/\"Example "
                          f"N\") -- replace it with a real, descriptive heading naming the "
                          f"actual developer task this example performs",
                "heading": heading_text,
            })
        normalized = heading_text.lower()
        if normalized in seen_heading_texts:
            findings.append({
                "reason": f"heading {heading_text!r} is used more than once inside \"View "
                          f"Additional Examples\" -- every example needs a distinct heading",
                "heading": heading_text,
            })
        seen_heading_texts[normalized] = seen_heading_texts.get(normalized, 0) + 1
    return findings


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
# A backtick token with no alphanumeric character at all (e.g. a lone `-` used as a formats
# table "unsupported" placeholder, per this project's own Markdown table convention) cannot be
# a class/method/file/command fingerprint by construction -- it is punctuation, not an
# identifier -- yet plain substring containment (`tok in unit`, in
# check_no_upstream_issue_leaked_into_readme) makes it match almost every bulleted line in a
# README (each starts with "- "), silently collapsing the intended 2-distinct-token threshold
# down to "1 real token + near-universal noise." Found live 2026-08-20 on slides/net:
# upstream-issues.md's SaveFormat-ignored entry backtick-quotes both `-` (a formats.md table
# cell) and `format`; `format` alone then spuriously concurs with an unrelated Key Capabilities
# bullet ("...character-level *formatting* via `PortionFormat`...") only because `-` supplied
# the second "hit" via substring match on that bullet's own leading markdown dash -- not
# because the bullet restates anything from upstream-issues.md. (The candidate's real,
# sanctioned plain-pointer disclosure of that same defect, "Saving currently always produces
# PPTX content...", never uses the word "format" and correctly does not trip this check either
# way.) Filtered structurally, not by name, since no fixed exclusion list can anticipate every
# punctuation-only table placeholder a future upstream-issues.md entry might quote.
_PUNCTUATION_ONLY_TOKEN_RE = re.compile(r"^\W+$")

_UPSTREAM_ISSUE_ENTRY_RE = re.compile(
    r"^##\s+(.+?)\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL
)


def split_upstream_issue_entries(upstream_issues_text: str) -> list[tuple[str, str]]:
    """Real, shared library call (2026-08-19, Fifty-Seventh incident / MT057, TC-UIW-04) --
    factored out of `_extract_upstream_issue_fingerprints`'s own, previously-inline split logic
    so the new upstream-issue-workflow module's Stage-1 ingestion reuses the exact same
    `## {title}` entry boundary this checks module already relies on, rather than a second,
    silently-divergent copy of the same regex. Returns one `(title, body)` pair per real `##`
    entry, in document order -- `title` is the heading's own text verbatim (numbered-heading
    products like `## 1. Old README instructs...` keep their leading "1. " here; callers that
    care about the bare title strip it themselves, since whether to strip is a caller-specific
    judgment, not something this shared split step should decide for every consumer).

    Works unchanged for both real upstream-issues.md variants this portfolio carries (Variant A:
    `## {title}` + Severity/Evidence/Impact/Not-fixable-here-because; Variant B: `## {N}. {title}`
    + Severity/Evidence only) -- both use plain `##` headings, the only structural assumption
    this function makes.
    """
    return [(m.group(1), m.group(2)) for m in _UPSTREAM_ISSUE_ENTRY_RE.finditer(upstream_issues_text)]


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

    Strips any ``` fenced code block out of the entry body BEFORE extracting single-backtick
    tokens (2026-08-16, Thirty-Seventh incident, found live while validating the new
    Installation/Quick-Start-scoped companion check against html/python's own real
    upstream-issues.md -- the exact motivating entry for this whole incident). A real Evidence
    bullet quoting a fenced ```toml snippet (three consecutive backticks) desyncs the naive
    single-backtick-pair regex: `[^`]+` cannot match across the triple-backtick boundary (each
    backtick in the fence is itself a zero-width gap to its neighbor), so the regex instead
    pairs backticks *around* the fence, capturing huge multi-line spans of surrounding prose as
    "tokens" while the real short tokens the fence's own prose refers to
    (`setuptools.backends`, `ModuleNotFoundError: No module named 'setuptools.backends'`, etc.)
    never get individually extracted at all. `_ANY_FENCED_CODE_RE` already exists for exactly
    this class of problem on the README side (`check_no_upstream_issue_leaked_into_readme`
    strips fenced code from the README before scanning it) -- this was simply never applied to
    the upstream-issues.md side of the same fingerprint pipeline.
    """
    fingerprints: list[set[str]] = []
    for _title, body in split_upstream_issue_entries(upstream_issues_text):
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
        body_no_fences = _ANY_FENCED_CODE_RE.sub("", body)
        raw_tokens = set(_ANY_BACKTICK_TOKEN_RE.findall(body_no_fences)) - _GENERIC_BACKTICK_EXCLUSIONS
        tokens = {tok for tok in raw_tokens if not _PUNCTUATION_ONLY_TOKEN_RE.match(tok)}
        tokens |= {m.group(0) for m in _COUNT_PHRASE_RE.finditer(body_no_fences)}
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

    `## Dependencies` (2026-08-20, TC-RDR-03-3D-TYPESCRIPT) joins the same exemption for the
    identical reason: MT041 added this section five days after this check first shipped, and a
    correctly-composed Dependencies bullet's own real name+version citation for any package an
    upstream-issues.md entry also documents will always concur on 2+ fingerprint tokens purely
    from stating the real fact, not from narrating the defect.
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
    # "Dependencies" (2026-08-20, TC-RDR-03-3D-TYPESCRIPT): the same "real reference, not
    # narration" reasoning already established for API Reference/Installation/Quick Start above
    # applies here too -- MT041 (2026-08-14) added this section five days after this check was
    # written, and it was never added to the exemption list. A real, correctly-composed
    # Dependencies bullet cites the exact package name AND exact version constraint (the
    # portfolio-wide established template), which for any dependency this product's own
    # upstream-issues.md also happens to document (e.g. 3d/typescript's `adm-zip` `^0.5.16`,
    # central to a real runtime-vs-devDependency packaging defect) will always concur on 2+
    # fingerprint tokens (the name plus the version) purely from stating the real fact -- found
    # live composing this exact product's real Dependencies section, not hypothetical.
    for excluded_heading in ("API Reference", "Installation", "Quick Start", "Dependencies"):
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


# --- Thirty-Seventh incident (2026-08-16): Installation/Quick Start leak blind spot ---
#
# check_no_upstream_issue_leaked_into_readme (above) deliberately excludes `## Installation`
# and `## Quick Start` from its scan -- a real, defensible design choice documented in that
# check's own docstring: those two sections exist specifically to give real, accurate
# instructions using real package/file/command names, so ordinary overlap with an
# upstream-issues.md entry's own evidence (which cites those same real names) is structurally
# expected there, not suspicious. But that exclusion means the two sections carry ZERO hard-
# gate leak protection -- confirmed live, `html/python`'s real `## Installation` section
# regressed into forensic, investigation-log narration (the exact broken build-backend string,
# the exact correct value, the exact `ModuleNotFoundError` message, an audit-style "every
# variant fails identically regardless of source" claim) duplicating a finding already
# correctly recorded in the sibling upstream-issues.md, and nothing caught it structurally --
# only a human reading the file by hand found it. `check_process_narration_smells` does scan
# these sections (it has no section exclusion), but it is `hard_gate: False` in
# readme_refresh_run.py -- advisory only, not something that can block a bad candidate from
# shipping -- so it never functioned as real protection here either.
#
# This check closes that specific blind spot WITHOUT reopening the reason the exclusion
# exists: unlike the broad `_PROCESS_NARRATION_PATTERNS` phrase list (built for prose sections
# where almost any internal-process phrasing is suspect), a phrase list that broad would
# false-positive constantly in Installation/Quick Start, where real commands legitimately look
# specific. Instead this reuses `_extract_upstream_issue_fingerprints`'s existing, already-
# validated structural signal (2+ concurring fingerprint tokens from the SAME upstream-issues.md
# entry) and adds a SECOND, independent, narrow requirement: at least one high-precision
# diagnostic-NARRATION signal, not just naming real things. A paragraph must satisfy BOTH before
# it is flagged -- fingerprints alone are expected and common in these two sections (a real
# command legitimately shares real names with upstream-issues.md's own evidence for it), so
# fingerprints alone are deliberately not sufficient here, unlike in the main check.
_INSTALL_QUICKSTART_NARRATION_PATTERNS = [
    # Comparative-correction framing: "the real/correct/actual X is Y, not Z" -- narrating
    # what a value SHOULD have been instead of just stating the real one.
    r"\bthe (?:real|correct|actual)\b[^.]{0,80}\bis\b[^.]{0,60},?\s+not\b",
    # Negative-existence claims about a named entity -- "is not a real module", "does not
    # exist in any real X release/version". A plain instruction never needs to assert what
    # something ISN'T; only a diagnostic narrative does.
    r"\b(?:is|are)\s+not\s+a\s+(?:real|separate)\b",
    r"\bdoes not exist in any\b",
    # Exhaustive-reproduction / scope-of-testing claims -- deliberately narrower than "at any
    # source" (a real, legitimate scope statement -- html/python's own fixed wording says
    # "fails for this repository at any source" and must never fire on that). Only the
    # stronger "regardless of X" / "every variant ... identically" framing, which narrates
    # exhaustive re-testing rather than just stating where a command works, counts.
    r"\bregardless of (?:source|install|the install)\b",
    r"\bevery\s+(?:variant|combination|install(?:ation)?\s*path)\b[^.]{0,60}\b(?:fails?|identically)\b",
    r"\bfails?\s+identically\b",
    # Root-cause-narration of WHY a failure happens, phrased as an investigation finding
    # rather than a plain instruction.
    r"\bbefore any of (?:this|the) (?:package|library|module)'?s own code\b",
]
_INSTALL_QUICKSTART_NARRATION_RE = re.compile(
    "|".join(_INSTALL_QUICKSTART_NARRATION_PATTERNS), re.IGNORECASE
)


def check_no_upstream_issue_leaked_into_install_or_quickstart(
    readme_text: str, upstream_issues_text: str
) -> list[dict]:
    """Hard gate (2026-08-16, Thirty-Seventh incident). Narrow companion to
    `check_no_upstream_issue_leaked_into_readme`, scoped ONLY to `## Installation` and
    `## Quick Start` -- the two sections that check deliberately excludes (see its own
    docstring, and the module-level comment directly above this function for the full
    incident trace).

    Reuses `_extract_upstream_issue_fingerprints` and `_iter_leak_scan_units` unchanged --
    same fingerprint-token extraction and same per-bullet/per-paragraph unit splitting as the
    main check. The difference is entirely in the flagging condition: a unit here is flagged
    only when it has BOTH (a) 2+ concurring fingerprint tokens from the same upstream-issues.md
    entry, the main check's existing signal, AND (b) at least one match against
    `_INSTALL_QUICKSTART_NARRATION_RE`, a small, high-precision phrase list scoped specifically
    to comparative-correction / negative-existence / exhaustive-reproduction framing -- not the
    broad, reactive `_PROCESS_NARRATION_PATTERNS` list `check_process_narration_smells` already
    uses (that list is deliberately not reused here: several of its own entries, e.g. `fails
    identically` used loosely, are tuned for prose sections and would risk over-firing against
    ordinary Installation-section specificity). Condition (b) is what keeps this check from
    reopening the false-positive risk the original exclusion exists to avoid: a real, specific
    command or package name alone (fingerprint overlap with no diagnostic narration) is exactly
    the "structurally expected, not suspicious" case the exclusion protects, so it must never
    fire on its own.

    No-op under the same conditions as the main check: empty/absent `upstream_issues_text`, or
    no extractable fingerprints.
    """
    if not upstream_issues_text:
        return []
    fingerprints = _extract_upstream_issue_fingerprints(upstream_issues_text)
    if not fingerprints:
        return []

    sections = _split_into_sections(readme_text)
    findings = []
    for heading in ("Installation", "Quick Start"):
        section_text = sections.get(heading)
        if not section_text:
            continue
        prose = _ANY_FENCED_CODE_RE.sub("", section_text)
        for unit in _iter_leak_scan_units(prose):
            if not _INSTALL_QUICKSTART_NARRATION_RE.search(unit):
                continue
            for fp_set in fingerprints:
                hits = {tok for tok in fp_set if tok in unit}
                if len(hits) >= 2:
                    findings.append({
                        "heading": heading,
                        "matched_tokens": sorted(hits),
                        "narration_phrase": _INSTALL_QUICKSTART_NARRATION_RE.search(unit).group(0),
                        "paragraph": unit.strip()[:200],
                        "reason": "this Installation/Quick Start paragraph both restates "
                                  "specific facts from a matching upstream-issues.md entry AND "
                                  "narrates the diagnostic story (comparative correction, "
                                  "negative-existence claim, or exhaustive-reproduction claim) "
                                  "instead of just giving the real working command -- forensic "
                                  "narration must live only in upstream-issues.md",
                    })
    return findings


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


def _extract_full_key_capabilities_bullets(readme_text: str) -> list[str]:
    """TC-HARDEN-40/41 (MT037, Twenty-Seventh incident, 2026-08-13). `check_key_capabilities_
    quality`'s own `re.findall(r"^-\\s+(.+)$", ..., re.MULTILINE)` only ever captures a
    bullet's FIRST physical line -- fine for bullet count/first-word/thinness, but the real
    portfolio convention wraps most Key Capabilities bullets longer than ~80 characters across
    2-4 physical lines (confirmed directly against `cells/java`'s own real, current section),
    so a check that needs the bullet's real ENDING (terminal punctuation) needs the full,
    joined text, not just its opening line. Groups each `- `-prefixed line with any following
    non-`- `-prefixed, non-blank continuation lines into one joined bullet string -- the same
    line-joining idiom already proven for `_iter_leak_scan_units` (TC-HARDEN-38), applied here
    to a section body that has no blank lines between bullets to begin with, so no block-level
    splitting is needed.
    """
    section_match = _KEY_CAPABILITIES_SECTION_RE.search(readme_text)
    if not section_match:
        return []
    bullets: list[str] = []
    current: "list[str] | None" = None
    for line in section_match.group(1).splitlines():
        if line.lstrip().startswith("- "):
            if current is not None:
                bullets.append(" ".join(current))
            current = [line.lstrip()[2:].strip()]
        elif line.strip() and current is not None:
            current.append(line.strip())
    if current is not None:
        bullets.append(" ".join(current))
    return bullets


def check_key_capabilities_structural_variety(readme_text: str) -> list[dict]:
    """Heuristic, non-blocking (2026-08-13, MT037 Item 4, Twenty-Seventh incident).
    `check_key_capabilities_quality` (above) already catches 3+ bullets sharing the identical
    literal first WORD -- it cannot see the broader "dry" pattern where every bullet opens
    with a *different* backtick-quoted identifier as its grammatical subject (e.g.
    `` `Style` carries...``, `` `Row` and `Column` support...``, `` `ValidationCollection`
    applies...`` -- distinct openings, identical monotonous shape). Confirmed live in
    `cells/java`'s real, pre-fix Key Capabilities section: 8 of 10 bullets opened this way.
    Flags when >=70% of bullets share this identifier-first shape -- a prompt to vary opening
    structure (identifier-first / action-first / benefit-first / task-first), never an
    automatic fail, since sentence-level prose style stays a human/agent judgment call,
    matching this module's established two-tier posture. The 70% threshold is a considered,
    not proven-optimal, first-iteration choice -- same disclosed posture as every other
    numeric threshold introduced in this module.
    """
    bullets = _extract_full_key_capabilities_bullets(readme_text)
    if not bullets:
        return []
    identifier_first = [b for b in bullets if re.match(r"^`[^`]+`", b)]
    ratio = len(identifier_first) / len(bullets)
    if ratio >= 0.7:
        return [{
            "reason": f"{len(identifier_first)} of {len(bullets)} bullets ({ratio:.0%}) open "
                      "with a backtick-quoted identifier as their grammatical subject -- "
                      "monotonous, API-reference-style structure; vary opening shape across "
                      "bullets (action-first, benefit-first, task-first, not just "
                      "identifier-first)",
            "identifier_first_bullets": identifier_first,
        }]
    return []


def check_key_capabilities_formatting(readme_text: str) -> list[dict]:
    """Heuristic, non-blocking (2026-08-13, MT037 Item 5, Twenty-Seventh incident). "Properly
    formatted," made mechanical and cheap. Reuses the proven backtick-parity-count idiom
    already established for `_has_stripped_example` (an odd count of backtick characters in
    one bullet means an unpaired backtick -- a real, common typo class, not a stylistic
    nitpick). Also flags a bullet not ending in terminal punctuation and a bullet whose first
    character is a lowercase letter that is not itself the start of a backtick-quoted
    identifier. Operates on the FULL, line-joined bullet text (`_extract_full_key_
    capabilities_bullets`), not just each bullet's first physical line -- a naive first-line-
    only check would false-positive on the terminal-punctuation rule for every bullet that
    wraps its closing sentence onto a later line, which is the near-universal real shape in
    this portfolio.
    """
    bullets = _extract_full_key_capabilities_bullets(readme_text)
    findings: list[dict] = []
    for bullet in bullets:
        if bullet.count("`") % 2 == 1:
            findings.append({"reason": "unmatched backtick in bullet", "bullet": bullet})
        if bullet and not bullet.rstrip().endswith((".", "!", "?", ":")):
            findings.append({
                "reason": "bullet does not end with terminal punctuation", "bullet": bullet,
            })
        first_char = bullet[0] if bullet else ""
        if first_char.isalpha() and first_char.islower():
            findings.append({
                "reason": "bullet starts with a lowercase letter (not a backtick-quoted "
                          "identifier)",
                "bullet": bullet,
            })
    return findings


def build_seo_keyword_placement_plan(seo_keywords_filtered: list[str], family: str) -> list[dict]:
    """readme-refresh-seo-deps-headings-hardening mission (2026-08-19): a typed, evidence-backed
    keyword placement PLAN, not just a filtered candidate POOL. Closes the disclosed gap named
    in this module's own SEO section: `filter_relevant_seo_keywords` (TC-HARDEN-39, above) only
    ever curates which phrases are relevant at factpack-build time -- nothing recorded what
    section a phrase was intended for, or later verified the composed text actually used any of
    them (see `check_seo_keyword_plan_usage`, below). Called identically from `plan_run`
    (factpack build) and `_run_deterministic_checks` (fresh recompute, matching this pipeline's
    own established "never trust a persisted factpack.json for a live check" pattern) -- a pure,
    stateless transform, so recomputing it costs nothing and never drifts from the factpack copy.

    Honest, disclosed limit: `priority` is always `"preferred"`, never `"required"`. This
    pipeline has no reliable capability-to-keyword mapping that would justify a stronger claim
    -- `filter_relevant_seo_keywords` only proves a phrase is grounded in the family name, a
    known real format, or established capability-verb vocabulary, not that it maps to one
    SPECIFIC verified capability. Inventing that mapping under this mission's own scope would be
    exactly the kind of overclaimed determinism the mission's own instructions warned against;
    a future enhancement could add a real "required" tier once such a mapping exists. Every
    phrase stays optional, natural-language color, matching the skill's own "never force a
    phrase into every bullet" rule -- `max_uses` is a ceiling, not a mandate.
    """
    return [
        {
            "phrase": phrase,
            "source_registry": f"keywords/{family}.json",
            "applicable_capability": None,  # honest gap -- see docstring; not yet computed
            "intended_section": "Key Capabilities",
            "reader_search_intent": "a developer searching for a free/open-source library with this capability",
            "priority": "preferred",
            "max_uses": 1,
        }
        for phrase in seo_keywords_filtered
    ]


def check_seo_keyword_plan_usage(readme_text: str, seo_keyword_plan: list[dict]) -> list[dict]:
    """Heuristic/advisory (readme-refresh-seo-deps-headings-hardening mission, 2026-08-19) --
    deliberately NEVER a hard gate, per this module's own explicit "never turn subjective prose
    quality into a simplistic hard keyword-count gate" instruction (TC-HARDEN-39 section,
    above). Confirmed real, live gap this closes: nothing in this pipeline ever cross-referenced
    `seo_keywords_filtered` against the actually-composed candidate text -- 3d/net's own real
    Key Capabilities section used zero of its 10 correct, real, `.NET`-scoped SEO phrases, and
    nothing flagged that.

    Lexical-overlap detection, not exact-phrase matching -- natural paraphrase is expected and
    correct (this module already prohibits verbatim keyword-list stuffing elsewhere). A phrase
    "counts as used" when at least one of its own significant (4+ letter) words appears anywhere
    in the candidate text, reusing the same `_WORD_RE` significant-word idiom already
    established for `check_key_capabilities_quality`'s bullet-length heuristic; a phrase with no
    4+-letter words at all (rare, very short phrases) falls back to any-word overlap. WARNs only
    when the plan is non-empty and LITERALLY ZERO phrases show any overlap anywhere in the
    document -- a floor against total non-engagement, never a per-bullet or per-phrase count.
    The plan itself can legitimately be empty (confirmed live for `cells/java`: all 10 raw
    phrases were contaminated and none survived `filter_relevant_seo_keywords`) -- that is not
    itself a finding.
    """
    if not seo_keyword_plan:
        return []
    text_lower = readme_text.lower()
    for entry in seo_keyword_plan:
        phrase = entry.get("phrase", "")
        significant_words = [w.lower() for w in _WORD_RE.findall(phrase)]
        words_to_check = significant_words or re.findall(r"[A-Za-z]+", phrase.lower())
        if any(word in text_lower for word in words_to_check):
            return []
    return [{
        "reason": f"{len(seo_keyword_plan)} SEO keyword phrase(s) were filtered as relevant for "
                  f"this product, but none show any lexical evidence of use anywhere in the "
                  f"composed candidate -- review whether the Intro/Key Capabilities prose "
                  f"should weave in some of this real, verified vocabulary",
        "plan_size": len(seo_keyword_plan),
    }]


def _extract_section_intro_prose(section_body: str) -> str:
    """New (2026-08-15, MT046, Thirty-Sixth incident / TC-HARDEN-71). Given a section's own
    captured body (everything after its `##` heading up to the next `##`, i.e. a
    `_KEY_CAPABILITIES_SECTION_RE`/`_EXAMPLES_SECTION_RE` `group(1)`), returns the leading
    prose -- the text before the first `- `-prefixed bullet line, the first fenced code
    block, or the first `###` sub-heading, whichever comes first. Empty string when real
    content starts immediately, the common, already-correct case for many products with no
    framing sentence at all (e.g. `barcode/python`, `cells/python`'s Key Capabilities). A
    small, reusable, single-purpose extractor, not a new parser -- mirrors the same "group
    until the first structural marker" idiom already used by
    `_extract_full_key_capabilities_bullets` and `_iter_leak_scan_units`.
    """
    lines: list[str] = []
    for line in section_body.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("```") or stripped.startswith("###"):
            break
        lines.append(line)
    return "\n".join(lines).strip()


# 2026-08-15 (MT046, Thirty-Sixth incident): a new, previously-unnamed-outside-API-Reference
# variant of MT039's "generation-mechanism/design-rationale narration" category -- a section's
# own intro sentence describing THIS DOCUMENT's own editorial/organizational choices or leaking
# an internal source-code structural fact, instead of stating a real product fact. Confirmed
# live in `font/python`'s real, captured Key Capabilities intro: "...grouped by real module
# rather than by workflow label. ...both covered inline via backtick-quoted class/command names
# below... (`instancing.py` alone is the largest module in the library)." Deliberately narrow
# (precision over recall, same posture as every other narration-pattern list in this module):
# a bare "grouped by X" is never flagged on its own -- the real, legitimate portfolio convention
# (`email/cpp`: "Features are grouped below by processing layer, from low-level CFB container
# access up through the high-level `mapi_message` API.") uses exactly that phrasing for a real
# product-architecture fact, and must never trip this check. Each pattern below was individually
# verified this incident against that real sentence (silent) and its siblings (`email/python`,
# `slides/*`, `pdf/cpp`) before being trusted.
_SECTION_INTRO_META_NARRATION_PATTERNS = [
    r"\brather than by\b",
    r"\bworkflow label\b",
    r"\bcovered inline\b",
    r"\b(?:highlights|snapshot)\b[^.]{0,60}\b(?:below|above)\b",
    r"`[\w./-]+\.(?:py|c|cc|cpp|cs|java|go|rs|ts|tsx|h|hpp)`\s*(?:alone\s+)?"
    r"is the (?:largest|biggest|smallest)\b",
    r"\bthe (?:largest|biggest) module\b",
]
_SECTION_INTRO_META_NARRATION_RE = re.compile(
    "|".join(_SECTION_INTRO_META_NARRATION_PATTERNS), re.IGNORECASE
)


def check_section_intro_no_meta_narration(readme_text: str) -> list[dict]:
    """Hard gate (2026-08-15, MT046, Thirty-Sixth incident / TC-HARDEN-71). Scans the leading
    intro prose (per `_extract_section_intro_prose`) of `## Key Capabilities` and `##
    Additional Examples` -- the two sections confirmed to share this section-intro-sentence
    shape and confirmed (Stage 4's own portfolio scan) to have zero dedicated intro-sentence
    coverage of any kind. `## API Reference`'s own intro sentence is deliberately excluded --
    it already has its own, separate, adequate coverage
    (`check_api_reference_classes_exist_in_reference_site`'s bad-pattern half plus MT039's
    `_PROCESS_NARRATION_PATTERNS` additions), and duplicating that here would risk two
    diverging rule sets for the same section.

    Neither `check_key_capabilities_quality`/`_structural_variety`/`_formatting` nor
    `check_process_narration_smells` ever inspected this text before this incident --
    confirmed by direct code read: every Key-Capabilities check extracts ONLY `^-\\s+` bullet
    lines, and the fixed-phrase-list narration checker never saw the real, captured `font/
    python` sentence's actual wording (a lexically disjoint phrasing of the same underlying
    idea `check_process_narration_smells`'s own MT039 addition already targets for a different
    section). This is not a phrase-list gap alone -- it is a genuine structural blind spot,
    closed here directly rather than by further widening an unrelated function's own pattern
    list.

    Deliberately precision-first, not exhaustive -- cannot prove no instance of this defect
    class exists anywhere in the portfolio, only that these three specific, evidence-backed
    patterns don't match. A differently-worded document-structure-narration sentence would
    still evade it, the same honest limit already disclosed for every other fixed-pattern
    narration check in this module.
    """
    findings: list[dict] = []
    for section_name, section_re in (
        ("Key Capabilities", _KEY_CAPABILITIES_SECTION_RE),
        ("Additional Examples", _EXAMPLES_SECTION_RE),
    ):
        section_match = section_re.search(readme_text)
        if not section_match:
            continue
        intro = _extract_section_intro_prose(section_match.group(1))
        if not intro:
            continue
        match = _SECTION_INTRO_META_NARRATION_RE.search(intro)
        if match:
            findings.append({
                "section": section_name,
                "reason": "section intro sentence narrates this document's own editorial/"
                          "organizational choices or leaks an internal source-file fact "
                          "instead of stating a real product fact (Thirty-Sixth incident, "
                          "MT046) -- see skills/readme-refresh.md's composition guidance "
                          "for the BAD/GOOD worked pair",
                "matched_phrase": match.group(0),
                "intro": intro,
            })
    return findings


_SEO_KEYWORD_PLATFORM_TOKENS = {
    # TC-HARDEN-39 (MT037, Twenty-Seventh incident, 2026-08-13): a small, explicit platform/
    # language token map defending against a real, confirmed cross-platform contamination
    # defect in keywords/{family}.json -- every non-.NET platform entry checked for the
    # `cells` family (java/python/rust, across products/docs/kb.aspose.org's own per-page
    # entries) carries keyword phrases naming .NET/C# instead of its own real platform (e.g.
    # `cells/java`'s own products.aspose.org entry: 10 of 10 keyword phrases mention .NET/C#,
    # zero mention Java). First-iteration, disclosed as incomplete -- confirmed only against
    # the `cells` family; other families not exhaustively checked.
    "net": (".net", "c#", "csharp", "dotnet"),
    "java": ("java",),
    "python": ("python",),
    "rust": ("rust",),
    "go": ("golang", " go ", " go,", " go."),
    "cpp": ("c++", "cpp"),
    "typescript": ("typescript",),
}


def _seo_keyword_wrong_platform(keyword: str, platform: str) -> bool:
    """True if `keyword` names a real platform/language token OTHER than `platform`'s own --
    the mechanical defense against the confirmed `keywords/{family}.json` contamination
    documented on `_SEO_KEYWORD_PLATFORM_TOKENS` above.

    Real bug found live on `cells/typescript` (the first genuinely new product this filter
    ever ran against): the original condition required the OTHER platform's token to be
    present AND this platform's own token to be ABSENT -- so a mixed phrase naming both
    (`"Aspose.Cells for .NET TypeScript library"`, real, live keywords/cells.json content)
    was never flagged, since "typescript" being present satisfied the "own token present"
    escape clause regardless of the ".NET" contamination sitting right next to it. The
    correct rule is unconditional: ANY other-platform token anywhere in the phrase disqualifies
    it, independent of whether the correct platform is also named.
    """
    lowered = f" {keyword.lower()} "
    for other_platform, tokens in _SEO_KEYWORD_PLATFORM_TOKENS.items():
        if other_platform == platform:
            continue
        if any(tok in lowered for tok in tokens):
            return True
    return False


_SEO_KEYWORD_RELEVANCE_TERMS = (
    "open source", "free", "alternative", "library", "api", "read", "write", "convert",
    "create", "edit", "generate", "parse", "process", "manipulate", "export", "import",
)


def filter_relevant_seo_keywords(
    keywords: list[str], family: str, platform: str, known_format_names: "set[str] | None" = None,
) -> list[str]:
    """TC-HARDEN-39 (MT037, Twenty-Seventh incident, 2026-08-13). Mechanical relevance filter
    over a product's real `keywords/{family}.json` keyword list -- implements "do not over
    stuff, only use related keywords" as real code rather than a hope: (1) drops any phrase
    naming a real platform/language OTHER than this product's own (`_seo_keyword_wrong_
    platform` -- the confirmed contamination defense); (2) keeps only phrases that also
    contain the family name, a known real format name, or one of this portfolio's own
    established capability-verb/framing terms (`_SEO_KEYWORD_RELEVANCE_TERMS`) -- never
    surfaces a phrase whose relevance can't be grounded in something already real and
    verified, the same "verify before including" discipline this module applies everywhere
    else, now applied to keyword phrases; (3) caps the result to 6 phrases, a structural
    stuffing guard applied before any prose is drafted, not left to composition-time restraint
    alone.
    """
    known_format_names = known_format_names or set()
    kept: list[str] = []
    for keyword in keywords:
        if _seo_keyword_wrong_platform(keyword, platform):
            continue
        lowered = keyword.lower()
        grounded = (
            family.lower() in lowered
            or any(term in lowered for term in _SEO_KEYWORD_RELEVANCE_TERMS)
            or any(fmt.lower() in lowered for fmt in known_format_names)
        )
        if grounded:
            kept.append(keyword)
        if len(kept) >= 6:
            break
    return kept


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


_FROM_SCRATCH_CLAIM_RE = re.compile(r"\bfrom scratch\b", re.IGNORECASE)
_FROM_SCRATCH_DIAGRAM_RE = re.compile(r"from scratch", re.IGNORECASE)


def check_diagram_from_scratch_capability_labeled(readme_text: str) -> list[dict]:
    """Heuristic, non-blocking (2026-08-17). Real, confirmed motivating case: `words/net`'s
    Key Capabilities own first bullet correctly, explicitly states "Create documents from
    scratch with the full document object model..." (verified against real source --
    `Document()`'s parameterless constructor and `DocumentBuilder()` both genuinely build a
    blank document with no input file) -- but the At-a-Glance diagram's corresponding
    Capabilities node read only "Document creation and editing", giving no visible signal of
    the from-scratch capability at a glance, even though this exact fold-in convention (fold
    a non-hybrid product's from-scratch capability into an existing Capability node's own
    label, per the Template section's Rule 2d) was already established and applied to this
    same product once before (2026-08-06 fix) -- the label's own WORDING was never actually
    checked against the convention it was supposed to satisfy.

    Fires only when Key Capabilities prose makes an explicit "from scratch" claim (a real,
    verified fact per this check's own precision-first posture -- it never asserts the claim
    itself is true, only that the diagram fails to reflect it) and the diagram's own
    Capabilities-subgraph node labels contain no matching phrase anywhere. A hybrid-archetype
    product's own `StartingPoints` container is checked too (the established literal there is
    "Nothing — authored from scratch", e.g. `pdf/cpp`'s real diagram), since that container is
    the other place this plan's own convention allows the phrase to legitimately live. Never
    blocks -- whether a given wording makes the capability sufficiently visible "at a glance"
    is an editorial judgment call, the same two-tier posture as every other diagram-content-
    quality check in this module (`check_diagram_container_duplicates_capability`, etc.).
    """
    caps_match = _KEY_CAPABILITIES_SECTION_RE.search(readme_text)
    if not caps_match:
        return []
    bullets = _extract_full_key_capabilities_bullets(readme_text)
    if not any(_FROM_SCRATCH_CLAIM_RE.search(bullet) for bullet in bullets):
        return []

    mermaid_text = extract_mermaid_block(readme_text)
    if not mermaid_text:
        return []
    graph = parse_diagram(mermaid_text)
    diagram_labels = [
        label for node_id, label in graph.node_label.items()
        if graph.node_subgraph.get(node_id) in ("capabilities", "starting_points")
    ]
    if any(_FROM_SCRATCH_DIAGRAM_RE.search(label) for label in diagram_labels):
        return []
    return [{
        "reason": "Key Capabilities makes an explicit 'from scratch' claim, but no diagram "
                  "Capabilities or Starting Points node label mentions it -- the capability "
                  "is invisible at a glance",
    }]


_INVENTED_FILLER_RE = re.compile(
    r"\bno known limitations?\b"
    r"|\bno (?:current|currently[- ]known|disclosed) limitations?\b"
    r"|\b(?:this|the) (?:library|project|edition) has no limitations?\b"
    r"|\bthere are (?:currently )?no (?:known )?limitations?\b"
    r"|\bno limitations? (?:are|is) currently known\b"
    r"|\bno limitations? (?:have|has) been (?:identified|found)\b",
    re.IGNORECASE,
)


def check_scope_limitations_format(readme_text: str) -> list[dict]:
    """Hard gate (2026-08-09, MT029 Item 4). A 6-product sample found 0 of 6 using a bulleted
    list -- 5 of 6 were prose paragraphs, and the 1 real exception (`pdf/net`) already showed
    the target shape: a bulleted list (optionally with bold category sub-labels once there are
    enough items to group) followed by a plain-prose closing paragraph linking the Enterprise
    Edition. This check enforces that shape portfolio-wide -- it does not invent a new format,
    it generalizes the one real product that already had it right.

    Findings:
    - `not_a_list`: the section has non-bullet, non-Enterprise-paragraph prose -- the old
      prose-paragraph shape (a limitation claim written as a sentence instead of a `- ` line).
    - `enterprise_paragraph_is_bulleted`: the closing Enterprise-mention content is itself a
      bullet -- violates the user's explicit "this para should remain as it is" instruction
      (a plain paragraph, not absorbed into the limitations list).
    - `missing_enterprise_paragraph`: no plain-prose paragraph linking a real
      `products.aspose.com` Enterprise Edition URL follows the limitations list.
    - `invented_filler`: the section states, in any wording, that no limitations exist (e.g.
      "no known limitations") -- 2026-08-13, the cells/cpp upstream-issues.md-leak healing
      pass's own governing policy: when no verified public limitation exists, the bulleted
      list is simply absent (see the zero-bullet carve-out below), never filled with a
      sentence asserting the absence -- that sentence is itself unverifiable manufactured
      content, the same defect class as citing an internal finding.

    Zero-bullet carve-out (2026-08-13): a section with NO `- ` lines is `not_a_list` only if
    it also has prose beyond the closing Enterprise paragraph. A section whose only non-bullet
    content IS the Enterprise-paragraph sentence(s) is the valid shape for "no verified public
    limitation exists for this product" -- omitting the bulleted list is correct there, not a
    format violation, and must never be confused with the old prose-paragraph-limitations shape
    this check exists to reject.

    Bug fix (2026-08-15, MT045 / Thirty-Fifth incident, TC-HARDEN-68): bullet/non-bullet
    classification now goes through `_iter_leak_scan_units` (the same, already-hardened
    bullet-with-its-own-continuation-lines grouping this module already built for
    `check_no_upstream_issue_leaked_into_readme`, TC-HARDEN-38) instead of raw, un-grouped
    physical lines. The prior implementation stripped blank lines and classified each
    PHYSICAL line independently -- so a bullet's own wrapped continuation line (no `- `
    prefix of its own) landed in `non_bullet_lines` even when it was really the tail of a
    bulleted Limitations item, letting an Enterprise-link sentence appended directly to a
    bullet (no blank line first) silently read as `enterprise_in_prose=True`/
    `enterprise_in_bullet=False` -- the exact combination this check exists to catch, and
    confirmed live to have missed `barcode/python`'s real, exact defect (the Enterprise
    sentence embedded as a continuation of the "PDF rendering is not implemented" bullet).
    A naive "just group continuation lines" fix alone (without `_iter_leak_scan_units`'s own
    blank-line-first paragraph split) was directly simulated and shown to false-positive on
    `email/python`'s and `pdf/cpp`'s own already-correct, genuinely blank-line-separated
    Enterprise paragraphs -- reusing the whole function, not reimplementing half of it, is
    what keeps both directions correct.
    """
    section_match = _SCOPE_LIMITATIONS_SECTION_RE.search(readme_text)
    if not section_match:
        return []
    section_text = section_match.group(1)
    if not section_text.strip():
        return [{"reason": "empty_section", "detail": "Scope and Limitations section is empty"}]

    findings: list[dict] = []
    if _INVENTED_FILLER_RE.search(section_text):
        findings.append({
            "reason": "invented_filler",
            "detail": "Scope and Limitations must never assert that no limitations exist -- "
                      "when no verified public limitation exists, omit the bulleted list "
                      "entirely rather than stating its absence",
        })

    units = _iter_leak_scan_units(section_text)
    bullet_units = [unit for unit in units if unit.lstrip().startswith("- ")]
    non_bullet_units = [unit for unit in units if not unit.lstrip().startswith("- ")]

    if not bullet_units:
        # Sentence-level, not line-level: a single physical line can legitimately mix a real
        # limitation claim with the Enterprise mention in one sentence-run (the exact shape
        # `test_scope_limitations_format_flags_prose_paragraph_shape` guards against -- "This
        # project reads and writes XLSX only. For broader coverage, see [Enterprise
        # Edition](...)." is one non-bullet line, but only its SECOND sentence references the
        # Enterprise host). Any sentence that doesn't reference the Enterprise host is a
        # candidate prose-form limitation claim.
        non_bullet_text = " ".join(unit.replace("\n", " ") for unit in non_bullet_units)
        sentences = re.split(r"(?<=[.!?])\s+", non_bullet_text)
        non_enterprise_sentences = [
            s for s in sentences if s.strip() and not _ENTERPRISE_LINK_HOST_RE.search(s)
        ]
        if non_enterprise_sentences:
            findings.append({
                "reason": "not_a_list",
                "detail": "Scope and Limitations must be a bulleted list (one distinct "
                          "limitation per '- ' line), not prose paragraphs",
            })
            return findings
        # Zero bullets, and every remaining line is part of the Enterprise paragraph itself --
        # the valid "no verified public limitation exists" shape. Fall through to the
        # enterprise-paragraph placement checks below (still real checks: the paragraph must
        # exist, in prose, with a real link) rather than returning here.

    enterprise_in_bullet = any(_ENTERPRISE_LINK_HOST_RE.search(unit) for unit in bullet_units)
    enterprise_in_prose = any(_ENTERPRISE_LINK_HOST_RE.search(unit) for unit in non_bullet_units)

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
# Fifty-Sixth incident / MT056 (2026-08-18): scoped, convergent idempotency.
#
# Content-addressed BLOCK identity (sha256 over block text, stable heading slugs -- never a
# positional counter; the positional unit_id scheme is the confirmed root cause of the R-07
# disposition-drift regression class, see reports/_scratch/mt056_regression_ledger.md pattern 4)
# plus the three enforcement primitives the change-scope workflow in readme_refresh_run.py
# (declare-scope / accept-blocks / converge-verify) is built on:
#   - split_into_scope_blocks / compute_block_fingerprints: the block model.
#   - check_scope_compliance [hard gate when a scope is declared]: out-of-scope-diff gate --
#     any block that changed vs. the immutable scope baseline without being authorized fails.
#   - check_frozen_blocks_unchanged [hard gate when an acceptance registry exists]: frozen-block
#     gate -- a CONVERGED/FROZEN_ACCEPTED block whose live hash no longer matches its accepted
#     hash, without an authorizing scope, fails.
#   - check_diagram_label_geometry [HARD gate, superseding the advisory
#     check_diagram_label_token_length as the blocking guard]: label-bulk/clipping geometry.
# ==================================================================================================


_SCOPE_BLOCK_MERMAID_ID = "mermaid"
_SCOPE_BLOCK_PREAMBLE_ID = "__preamble__"


def _slugify_block_heading(heading: str) -> str:
    """Stable block id for a `##` section heading: lowercase, non-alphanumeric runs collapsed
    to single hyphens ("Key Capabilities" -> "key-capabilities"). Deliberately case-insensitive
    so the MT024 title-case migration class of change (pure re-casing) still maps to the same
    block identity; an actual RENAME is, by design, a remove+add of two different block ids and
    therefore needs both ids authorized in the scope (plus any dependent anchor/TOC blocks)."""
    slug = re.sub(r"[^a-z0-9]+", "-", heading.strip().lower()).strip("-")
    return slug or "untitled-section"


def split_into_scope_blocks(markdown_text: str) -> dict[str, str]:
    """Split a candidate README into stable, content-addressable blocks:

    - `"__preamble__"` -- everything before the first `##` heading (title/badges/banner/intro),
      exactly as `_split_into_sections` defines it.
    - `"mermaid"` -- the FIRST ```` ```mermaid ```` block in the document (fences included),
      exposed as its own block so a diagram-only scope can authorize the diagram without
      authorizing its host section's prose. The host section's own block text carries the
      placeholder in the diagram's position, so prose edits around the diagram are still
      attributed to the host section, never masked by the diagram's extraction.
    - one block per `##` section, keyed by `_slugify_block_heading(heading)`.

    Reuses `_split_into_sections` (H2-only boundaries; `###` subsections stay inside their
    owning section) and `_MERMAID_BLOCK_FULL_RE`/`_MERMAID_BLOCK_PLACEHOLDER` (the exact
    mechanism `check_only_mermaid_block_changed` has used since MT021) rather than inventing a
    third parser. A duplicate `##` heading collapses to one key -- the same already-known
    property `_split_into_sections` has; `check_required_sections`/duplicate-row gates keep real
    candidates free of duplicate H2s."""
    mermaid_match = _MERMAID_BLOCK_FULL_RE.search(markdown_text)
    working_text = markdown_text
    if mermaid_match:
        working_text = (
            markdown_text[: mermaid_match.start()]
            + _MERMAID_BLOCK_PLACEHOLDER
            + markdown_text[mermaid_match.end():]
        )
    sections = _split_into_sections(working_text)
    blocks: dict[str, str] = {}
    for heading, text in sections.items():
        if heading == "__preamble__":
            blocks[_SCOPE_BLOCK_PREAMBLE_ID] = text
        else:
            blocks[_slugify_block_heading(heading)] = text
    if mermaid_match:
        blocks[_SCOPE_BLOCK_MERMAID_ID] = mermaid_match.group(0)
    return blocks


def compute_block_fingerprints(markdown_text: str) -> dict[str, str]:
    """sha256 hex digest per scope block (UTF-8 of the block's exact text, newlines included).
    Content-addressed by construction: editing any byte of a block changes its fingerprint;
    reordering or renaming other blocks never does."""
    return {
        block_id: hashlib.sha256(text.encode("utf-8")).hexdigest()
        for block_id, text in split_into_scope_blocks(markdown_text).items()
    }


def check_scope_compliance(
    baseline_markdown_text: str,
    candidate_markdown_text: str,
    authorized_block_ids: list[str],
) -> list[dict]:
    """Out-of-scope-diff HARD gate (MT056). Compares the candidate against the scope's own
    IMMUTABLE baseline snapshot (captured at declare-scope time -- never the rolling
    last-checked snapshot, which is overwritten as iterations proceed) and fails on any block
    that changed, appeared, or disappeared without being authorized.

    `authorized_block_ids` is the union of the scope's `areas` and `allowed_dependencies` --
    the caller merges them; this function does not distinguish the two (both are authorized;
    the distinction is documentation of intent in the scope record itself).

    Returns `{"block_id", "change", "reason"}` findings; empty iff every unauthorized block is
    byte-identical to the baseline. This is deliberately the same proof shape as
    `check_only_sections_changed`, upgraded to (a) content-addressed block ids including the
    `mermaid` pseudo-block, and (b) an immutable baseline, closing the R-10-adjacent defect
    where the rolling snapshot was overwritten even by a failed iteration."""
    baseline_blocks = split_into_scope_blocks(baseline_markdown_text)
    candidate_blocks = split_into_scope_blocks(candidate_markdown_text)
    authorized = set(authorized_block_ids)
    findings: list[dict] = []
    for block_id in sorted(set(baseline_blocks) | set(candidate_blocks)):
        if block_id in authorized:
            continue
        old_text = baseline_blocks.get(block_id)
        new_text = candidate_blocks.get(block_id)
        if old_text == new_text:
            continue
        if old_text is None:
            change = "added"
        elif new_text is None:
            change = "removed"
        else:
            change = "modified"
        findings.append({
            "block_id": block_id,
            "change": change,
            "reason": f"block {block_id!r} was {change} but is not authorized by the active "
                      "change scope (areas + allowed_dependencies); declare it before "
                      "regeneration or revert the collateral change",
        })
    return findings


_FROZEN_BLOCK_STATUSES = frozenset({"CONVERGED", "FROZEN_ACCEPTED"})
_ACCEPTANCE_BLOCK_STATUSES = frozenset({
    "ACTIVE_IMPROVEMENT",
    "CONVERGED",
    "FROZEN_ACCEPTED",
    "INVALIDATED_BY_SOURCE_CHANGE",
    "BLOCKED",
    "NEEDS_REVIEW",
})


def check_frozen_blocks_unchanged(
    candidate_markdown_text: str,
    registry_entries: list[dict],
    authorized_block_ids: "list[str] | None" = None,
) -> list[dict]:
    """Frozen-block HARD gate (MT056). For every acceptance-registry entry whose status is
    CONVERGED or FROZEN_ACCEPTED, the candidate's live block fingerprint must equal the
    recorded `accepted_sha256` -- unless the block is authorized by the active change scope
    (`authorized_block_ids`), in which case the change is a deliberate, declared reopening and
    the registry entry is expected to be re-accepted (or invalidated) before the run closes.

    A frozen block that has VANISHED from the candidate is also a finding -- deletion is a
    change. Malformed entries (unknown status, missing accepted_sha256) are findings too:
    fail-closed, never skip-silently (the R-01 prose-only-rule class)."""
    authorized = set(authorized_block_ids or [])
    live = compute_block_fingerprints(candidate_markdown_text)
    findings: list[dict] = []
    for entry in registry_entries:
        block_id = entry.get("block_id")
        status = entry.get("status")
        if not isinstance(block_id, str) or not block_id:
            findings.append({
                "block_id": str(block_id),
                "reason": "acceptance-registry entry has no valid block_id",
            })
            continue
        if status not in _ACCEPTANCE_BLOCK_STATUSES:
            findings.append({
                "block_id": block_id,
                "reason": f"acceptance-registry status {status!r} is not one of the defined "
                          f"states {sorted(_ACCEPTANCE_BLOCK_STATUSES)}",
            })
            continue
        if status not in _FROZEN_BLOCK_STATUSES:
            continue
        if block_id in authorized:
            continue
        accepted = entry.get("accepted_sha256")
        if not isinstance(accepted, str) or len(accepted) != 64:
            findings.append({
                "block_id": block_id,
                "reason": f"{status} entry carries no valid accepted_sha256 -- a frozen block "
                          "without a recorded fingerprint cannot be verified and fails closed",
            })
            continue
        current = live.get(block_id)
        if current is None:
            findings.append({
                "block_id": block_id,
                "status": status,
                "reason": f"{status} block {block_id!r} is absent from the candidate -- "
                          "deleting an accepted block requires an authorizing change scope",
            })
        elif current != accepted:
            findings.append({
                "block_id": block_id,
                "status": status,
                "accepted_sha256": accepted,
                "current_sha256": current,
                "reason": f"{status} block {block_id!r} changed without an authorizing change "
                          "scope -- accepted content must remain byte-identical until a scope "
                          "explicitly reopens it",
            })
    return findings


_DIAGRAM_LABEL_CHARS_PER_LINE = 26
_DIAGRAM_LABEL_MAX_EST_LINES = 3


def _estimate_wrapped_lines(label: str, chars_per_line: int) -> int:
    """Greedy word-wrap estimate of how many lines a node label renders across at Mermaid's
    ~200px foreignObject width (~26 average-width chars/line in the GitHub default font).
    Models `white-space: break-spaces` faithfully in the one way that matters: wrapping happens
    ONLY at whitespace -- an unbroken token longer than the line budget still occupies (and
    overflows) a single line, exactly the mermaid-js/mermaid#6424 behavior. An approximation by
    construction (real glyph widths vary); thresholds are corpus-grounded, see
    check_diagram_label_geometry."""
    lines = 1
    current = 0
    for token in label.split():
        width = len(token)
        if current == 0:
            current = width
        elif current + 1 + width <= chars_per_line:
            current += 1 + width
        else:
            lines += 1
            current = width
    return lines


def check_diagram_label_geometry(
    markdown_text: str,
    max_token_chars: int = _DIAGRAM_LABEL_MAX_TOKEN_CHARS,
    chars_per_line: int = _DIAGRAM_LABEL_CHARS_PER_LINE,
    max_lines: int = _DIAGRAM_LABEL_MAX_EST_LINES,
) -> list[dict]:
    """HARD gate (MT056, Fifty-Sixth incident, 2026-08-18): diagram label geometry -- the
    blocking successor to the advisory `check_diagram_label_token_length` (which stays in place
    unchanged as the historical, non-blocking form; this gate subsumes its rule).

    Two clauses, both mechanical:
      1. TOKEN OVERFLOW -- any single whitespace-delimited token longer than `max_token_chars`
         (28): `break-spaces` never breaks mid-word (mermaid-js/mermaid#6424), so an unbroken
         token wider than the ~200px node budget clips, full stop. Corpus-grounded: the longest
         real, render-verified-safe tokens are 21/20 chars; the longest anywhere in the live
         62-file corpus is 24 (`PPTM/PPSX/PPSM/POTX/POTM`).
      2. LABEL TOO TALL -- a label whose greedy word-wrap estimate exceeds `max_lines` (3) at
         `chars_per_line` (26). This is the previously-unguarded adjacent class behind the real
         2026-08-05 "oversized Outputs box" complaint (R-01) and the exact drift direction the
         regen-full tree measurably exhibits (labels >40 chars grew 108 -> 130 across the tree;
         max label 90 chars, ~4+ rendered lines). At 26 chars/line, 3 lines comfortably holds
         ~78 chars of normal prose -- every render-verified-clean label in the corpus fits;
         the known-oversized real labels (page/python c5 at 90, slides/net c2 at 86) fail.

    Same label surface as the advisory check: node labels AND subgraph container titles.
    No mermaid block -> no findings (`check_diagram_shape` separately hard-requires the
    diagram's existence via the required-section family)."""
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []
    graph = parse_diagram(mermaid_text)
    findings: list[dict] = []

    labels: list[tuple[str, str]] = [
        (node_id, label) for node_id, label in graph.node_label.items()
    ]
    for line in mermaid_text.splitlines():
        title_match = _SUBGRAPH_START_RE.match(line.strip())
        if title_match and title_match.group(2):
            labels.append((title_match.group(1), title_match.group(2)))

    for label_id, label in labels:
        for token in label.split():
            stripped = token.strip(".,;:()[]{}\"'")
            if len(stripped) > max_token_chars:
                findings.append({
                    "node_id": label_id,
                    "label": label,
                    "kind": "token_overflow",
                    "token": stripped,
                    "token_length": len(stripped),
                    "reason": f"token {stripped!r} ({len(stripped)} chars) exceeds the "
                              f"{max_token_chars}-char unbreakable-token ceiling and will clip "
                              "on renderers that cannot break mid-word (mermaid#6424)",
                })
        est_lines = _estimate_wrapped_lines(label, chars_per_line)
        if est_lines > max_lines:
            findings.append({
                "node_id": label_id,
                "label": label,
                "kind": "label_too_tall",
                "label_length": len(label),
                "estimated_lines": est_lines,
                "reason": f"label ({len(label)} chars, ~{est_lines} wrapped lines at "
                          f"~{chars_per_line} chars/line) exceeds the {max_lines}-line node "
                          "budget -- shorten the label or move detail into Key Capabilities "
                          "prose; oversized nodes are the confirmed R-01 legibility defect",
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
# 2026-08-16: markdown link text/target were entirely invisible to every prior pattern above --
# none of backtick/CamelCase-ALLCAPS/version/quoted-string shape matches `[text](target)`
# syntax. Found live: html/python's u0032 ("For the stable API summary, see [PUBLIC_API.md]
# (PUBLIC_API.md). For runnable scenarios, see [examples](examples).") extracted only a single,
# generic "API" token (a stray ALLCAPS fragment of "PUBLIC_API.md", not a deliberate match) --
# giving `check_content_unit_merged_into_target_section`'s otherwise-correct per-sentence-group
# verification (MT049) nothing real to check the second sentence against, so a disposition
# claiming BOTH facts landed in "Documentation & Resources" passed even though the "examples"
# fact actually landed in a different section (Additional Examples) -- a real content-location
# discrepancy the check should have (and, once this lands, will) catch. Two separate single-group
# patterns, matching the module's own existing convention of one capture group per pattern rather
# than a two-group findall (which would return tuples, breaking `_extract_salient_tokens`'s
# `token.strip()` call).
#
# A leading `!` (image syntax, `![alt](path.png)`) IS excluded via the negative lookbehind --
# found live during this same fix's own portfolio-wide sanity sweep, immediately after landing
# the plain-link patterns above: `page/python`'s real u0014/u0015 excerpts are pure image
# references (`![ps2pdf result](readme.resources/TestImages.png)`) whose alt text/filename were
# never going to appear as literal prose anywhere -- an earlier, independent fix pass had already
# hand-removed exactly this filename from u0015's own token list for this exact reason (a
# fused-portmanteau false positive, MT049-era), and the plain-link patterns would have silently
# reintroduced the identical false-positive class in a new guise had this exclusion not been
# added before the fix was trusted. A real image *fact* (what it depicts) still gets its own
# distinct content unit and dispositioning elsewhere in this pipeline -- this exclusion only
# stops an image's raw alt text/filename from being treated as a prose-checkable identifier.
_SALIENT_LINK_TEXT_RE = re.compile(r"(?<!!)\[([^\]]+)\]\([^)]+\)")
_SALIENT_LINK_TARGET_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def _extract_salient_tokens(excerpt: str) -> list[str]:
    """Seed extractor for a content unit's checkable identity -- backtick spans, CamelCase/
    ALLCAPS identifier-shaped tokens, quoted names, version numbers, and (2026-08-16) markdown
    link text/targets. Explicitly disclosed as incomplete, same posture as
    `_DIAGRAM_SUPPLEMENTARY_FORMAT_NAMES`/`_CONTAINER_CONNECTOR_ALLOWLIST` elsewhere in this
    module -- exists to give `check_content_unit_merged_into_target_section` something
    mechanically checkable, not to summarize meaning. Order-preserving, case-insensitive
    de-duplication.
    """
    tokens: list[str] = []
    for pattern in (
        _SALIENT_BACKTICK_RE, _SALIENT_IDENTIFIER_RE, _SALIENT_VERSION_RE, _SALIENT_QUOTED_RE,
        _SALIENT_LINK_TEXT_RE, _SALIENT_LINK_TARGET_RE,
    ):
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
    "5_dependency_claim",  # Thirty-First incident / MT041 (2026-08-14) -- a real old-README
    # dependency-shaped claim (extended, not a new sibling file, per this incident's own
    # investigation: unlike structure-dispositions.json/badge-dispositions.json, dependency
    # prose has no structural blindness in extract_old_readme_content_units -- it's ordinary
    # sentence content already reached by the existing extraction).
})
_CONTENT_UNIT_DISPOSITIONS = frozenset({
    "merged_verbatim", "merged_reframed", "excluded",
    "corrected",  # MT041: distinct from merged_reframed (restated for fit) -- "this old claim
    # was factually wrong and got corrected against real manifest data."
})
_CONTENT_UNIT_VERIFICATION_STATUSES = frozenset({
    "verified_against_source", "verified_redundant", "not_applicable_category_1",
    "verified_by_corroboration",
    "verified_against_manifest",  # MT041: a categorically STRONGER standard than verified_
    # against_source -- a structured, mechanically-diffable DependencySnapshot match, not
    # prose-eyeballing. Symmetric with how 4_verifiable_history earned its own categorically
    # WEAKER verified_by_corroboration status rather than reusing an ill-fitting existing one.
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
#
# "Additional Examples" (2026-08-13, Twenty-Fourth mission/cells-go): also permanently OPTIONAL
# (never added to _REQUIRED_SECTIONS, same "vacuously satisfied" precedent as Project History
# above) but a real, legitimate merge target -- found live while reconciling cells/go's old
# per-example worked snippets, which naturally belong under this exact section (the same
# already-established portfolio-wide home for worked-example code, per the Template section's
# own flagship-example rule). _split_into_sections already resolves it correctly as a real H2
# section key with no code change needed; only this allowlist was blocking a real, honest
# disposition from validating.
#
# "Project Structure" (2026-08-13, Twenty-Fifth mission/cells-java): the SAME class of gap as
# "Additional Examples" above, found the same day -- a structural unit's own OLD heading (e.g.
# cells/java's real "Project Layout") is not always the exact heading the new candidate uses for
# the same content; the skill's own established, portfolio-wide standard name for this content
# class is "Project Structure" (already used this way for cells/go), so a rename from an old
# product-specific heading into this standard one is a real, legitimate "merged_reframed", not a
# drop. Also permanently OPTIONAL, same "vacuously satisfied" precedent.
_CONTENT_UNIT_TARGET_SECTIONS = frozenset(_REQUIRED_SECTIONS) | {
    "Intro", "Project History", "Additional Examples", "Project Structure",
    "Feature Showcase", "Navigation", "Third-Party Notices",
}
# MT056 follow-up (2026-08-18): "Navigation" was missing from this allowlist -- the same
# recurring "a real, always-present template section was never added to the allowlist" gap this
# plan has already found and fixed for Additional Examples/Project Structure/Feature Showcase.
# Found live on `pdf/cpp`: its 12 real ## Navigation TOC bullets are each their own legitimately
# merged_verbatim content unit (the product is byte-for-byte identical to its own old README, so
# every line -- Navigation included -- was extracted and merged verbatim), previously masked by
# MT053's own published-upstream bypass; the moment ANY edit makes the candidate diverge from
# published state, the full preservation-tracking battery re-activates and this gap surfaces.
#
# "Third-Party Notices" (2026-08-20, readme-disposition-remediation-2026-08-18 mission,
# TC-RDR-03-PDF-CPP): the SAME recurring gap again, same root cause -- a real, always-present
# `## Third-Party Notices` H2 (used by pdf/cpp and pdf/go for bundled-codec/font/GoogleTest
# licensing disclosures) was never added to this allowlist, so a genuine, correctly-targeted
# `merged_verbatim` disposition into that real section failed
# `check_content_unit_disposition_coverage` with "needs a real target_section" even though the
# candidate's own heading is right there. Not optional/vacuous like Additional Examples/Project
# Structure -- a product either has real third-party-bundled code to disclose or it doesn't --
# but the allowlist membership question is identical to every prior entry in this list.


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


def check_content_unit_excerpt_matches_extraction(
    content_units: list[dict], dispositions: list[dict]
) -> list[dict]:
    """Hard gate (MT048, note/python pilot, 2026-08-15). `extract_old_readme_content_units`'s own
    docstring discloses that `unit_id` is "a stable, order-based id... not a content hash" --
    MT030 Phase 2 (2026-08-10) already found this a real, recurring, previously ONLY-manually-
    caught defect class: recovering (or removing) a unit anywhere but the very end of the old
    README shifts every LATER unit's `unit_id` by one, and `check_content_unit_disposition_
    coverage`'s own unit_id-presence check cannot detect this -- a shifted id that happens to
    still exist in the current extraction passes that check cleanly even though it now points at
    completely different content than whatever a human/agent actually reviewed and disposed.
    Every prior instance of this drift (MT030 Phase 2's own 4-of-5 follow-up batches) was caught
    only via ad hoc, by-hand excerpt diffing against the live extractor -- a real, disclosed,
    NOT-yet-durably-fixed recurring hazard this plan's own history names directly.

    This closes it mechanically and permanently, reusing the excerpt text every disposition
    entry already stores as its own de facto content fingerprint -- no new schema field, no hash
    column, nothing to backfill across the portfolio: for every disposition whose `unit_id` still
    resolves in the current `content_units` extraction, compares the entry's OWN stored `excerpt`
    against the live extractor's excerpt for that same id (normalized via `_normalize_for_drop_
    match` -- emoji-stripped, casefolded, whitespace-collapsed, the same comparison `check_
    dropped_content`'s heading-rename tolerance already uses) and flags a mismatch as a real,
    current drift. A dangling/missing `unit_id` is `check_content_unit_disposition_coverage`'s
    own job, not repeated here -- this function is silent (not a duplicate finding) for any id
    absent from the live extraction.
    """
    findings: list[dict] = []
    units_by_id = {u["unit_id"]: u for u in content_units}
    for entry in dispositions:
        uid = entry.get("unit_id")
        live = units_by_id.get(uid)
        if live is None:
            continue
        stored_excerpt = (entry.get("excerpt") or "").strip()
        if not stored_excerpt:
            continue
        live_excerpt = (live.get("excerpt") or "").strip()
        if _normalize_for_drop_match(stored_excerpt) != _normalize_for_drop_match(live_excerpt):
            findings.append({
                "unit_id": uid,
                "stored_excerpt": stored_excerpt[:160],
                "live_excerpt": live_excerpt[:160],
                "reason": "disposition's own stored excerpt no longer matches the live "
                          "extractor's excerpt for this unit_id -- likely position-based "
                          "unit_id drift (an upstream README edit or an extractor fix shifted "
                          "later ids), or the old README genuinely changed under this id; "
                          "re-verify this disposition against the CURRENT excerpt before "
                          "trusting its classification/verification",
            })
    return findings


def _is_self_citation_of_root_readme(evidence_ref: str) -> bool:
    """MT055/TC-MICRO-04: True only for the bare root README filename (case-insensitive, no
    directory component) -- a real, different README belonging to a subdirectory (e.g.
    `examples/README.md`) is a genuinely independent file and must never be flagged."""
    normalized = str(evidence_ref).strip().replace("\\", "/")
    return "/" not in normalized and normalized.lower() == "readme.md"


def check_content_unit_evidence_resolves(
    dispositions: list[dict],
    clone_cache_root: str,
    package_registry: "dict | None" = None,
    docs_texts: "dict[str, str] | None" = None,
    reject_self_citation: bool = True,
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

    MT055/TC-MICRO-04 (2026-08-18): when `reject_self_citation` (default True), a `clone_cache_
    path` evidence_ref of the bare root README itself (`README.md`, case-insensitive, no
    directory component -- never a real, different README belonging to a subdirectory like
    `examples/README.md`) is REJECTED even though it technically resolves. Confirmed real during
    the MT054 preservation audit: ~40 of `pdf/net`'s 69 CONTENT-unit disposition entries cited
    `evidence_ref: "README.md"` as their own supporting evidence for a claim ABOUT the product
    (e.g. "supports rendering to PNG/JPEG/BMP") -- circular, not real verification, since the file
    always "exists" (it's the very document being audited) regardless of whether the claim is
    true. A hand sample of 9 of the ~40 found 1 real, confirmed factual failure hiding behind
    exactly this circular citation. This closes RC-C from that audit.

    `reject_self_citation=False` is required for structural- and code-example-unit callers
    (`structural_unit_evidence_resolves`/`code_example_evidence_resolves` in `_run_deterministic_
    checks`): those units represent VERBATIM EXTRACTIONS from the old README itself (a directory
    tree, a fenced bash command) rather than independently-checkable factual claims -- citing the
    README as the source of a literal excerpt is real, true provenance, not circular reasoning.
    Confirmed live: applying the self-citation rule unscoped broke this shared function's own
    test fixture (`_STRUCTURE_DISPOSITIONS_FOR_SHARED_FIXTURE`'s s0001, `_CODE_EXAMPLE_
    DISPOSITIONS_FOR_SHARED_FIXTURE`'s c0001, both legitimately citing README.md as the literal
    source of an extracted block) before this parameter was added.
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
        if (
            reject_self_citation
            and evidence_type == "clone_cache_path"
            and _is_self_citation_of_root_readme(evidence_ref)
        ):
            findings.append({
                "unit_id": entry.get("unit_id"),
                "evidence_type": evidence_type,
                "evidence_ref": evidence_ref,
                "reason": (
                    "evidence_ref cites the root README.md itself -- circular self-citation, "
                    "not real verification of a claim about that same document's content; cite "
                    "the real source file, class, or registry field the claim actually depends on"
                ),
            })
            continue
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


# TC-HARDEN-78 (MT047/Thirty-Seventh incident, 2026-08-15) -- see check_content_unit_merged_
# into_target_section's own docstring below for the full defect this closes.
_CANDIDATE_INDEPENDENT_STATEMENT_RE = re.compile(
    r"candidate'?s?\s+own\s+(?P<section>.+?)\s+independently\s+(?:states?|names?|covers?)",
    re.IGNORECASE,
)
_INDEPENDENT_STATEMENT_TRAILING_WORDS = frozenset({"section", "paragraph", "bullets", "bullet", "intro"})
_QUOTED_SINGLE_RE = re.compile(r"(?<=[\s(])'([^']{4,150})'(?=[\s).,;:]|$)")
_QUOTED_DOUBLE_RE = re.compile(r'"([^"]{4,150})"')
_NORMALIZE_FOR_CONTIGUOUS_MATCH_RE = re.compile(r"[\s\-]+")


def _extract_quoted_phrases(text: str) -> list[str]:
    """Every single- or double-quoted span in `text` (min 6 chars, to skip a bare quoted single
    word), in document order -- the real, established authoring convention for this free-text
    shape's own restated-claim phrase (e.g. `u0001`'s `('zero required third-party runtime
    dependencies')`)."""
    matches = [(m.start(), m.group(1)) for m in _QUOTED_SINGLE_RE.finditer(text)]
    matches += [(m.start(), m.group(1)) for m in _QUOTED_DOUBLE_RE.finditer(text)]
    matches.sort(key=lambda pair: pair[0])
    return [phrase for _pos, phrase in matches]


def _normalize_for_contiguous_match(text: str) -> str:
    """Lowercases and collapses both whitespace AND hyphens to a single space -- the real,
    confirmed-necessary normalization for `font/python`'s own quoted claims: `u0001`'s quoted
    `'zero required third-party runtime dependencies'` and the real Intro's own hyphenated
    `third-party` need hyphen/space equivalence to match as the same contiguous phrase."""
    return _NORMALIZE_FOR_CONTIGUOUS_MATCH_RE.sub(" ", text.strip().lower()).strip()


def _normalize_independent_statement_target(raw_section: str) -> str:
    """Strips a trailing descriptive word the free-text "candidate's own X independently
    states..." phrase commonly appends after the real heading name -- e.g. "Key Capabilities
    bullets" -> "Key Capabilities", "Development and Testing section" -> "Development and
    Testing", "Key Capabilities intro paragraph" -> "Key Capabilities" (two strips). These are
    the exact 3 distinct trailing shapes found live in `font/python`'s own real, current
    `content-dispositions.json` (`u0001`'s bare "Intro" needs no stripping at all). Deliberately
    simple, not a real heading-fuzzy-matcher -- same "presence not proof" posture as this
    module's other phrase-list extensions; an unresolvable phrase still produces a real,
    correctly negative downstream finding rather than a silent skip.
    """
    words = raw_section.strip().split()
    while words and words[-1].lower() in _INDEPENDENT_STATEMENT_TRAILING_WORDS:
        words.pop()
    normalized = " ".join(words).strip()
    return normalized or raw_section.strip()


# MT049 (Thirty-Ninth incident, 2026-08-15) -- see check_content_unit_merged_into_target_section's
# own docstring below for the full defect this closes: a compound, multi-sentence excerpt could
# pass on the strength of ONE bundled fact's token surviving into the target section while a
# DIFFERENT bundled fact was silently dropped from the merge.
#
# MT052 (Forty-Third incident, 2026-08-18) extends the split to a `;` immediately followed by a
# backtick-quoted, dotted-or-parenthesized identifier starting a new clause -- real, confirmed
# case: `pdf/go`'s own u0048, "`Document.JavaScript()` is the document-level named-script
# collection (`/Catalog/Names/JavaScript`); `Document.SetOpenAction` sets the action run when the
# document opens...", a semicolon-joined bullet bundling two distinct facts that MT049's own
# terminal-punctuation rule (`.`/`!`/`?` only) never split, letting the second fact's own
# SetOpenAction claim silently drop out of a merge while the first fact's own token kept the
# whole-excerpt check passing. Scoped deliberately narrow -- ONLY a semicolon followed by a
# backtick-quoted identifier, never a bare `;` -- and validated against a real, live negative-
# control sweep of every real disposition excerpt in the portfolio containing a `;` +
# backtick-identifier shape (25 real excerpts, both trees) before being trusted: every one of the
# other 24 is either already a genuinely separate fact (correctly split, no behavior regression
# since each half's own tokens already independently corroborate in the target section) or a
# lumped comma/semicolon-joined enumeration of same-shaped items (`Document.NUp`/`Document.
# Booklet`, `SearchText`/`ReplaceText`, `AddTextField`/... , etc.) where splitting is likewise
# harmless because BOTH halves' own distinctive tokens are already present together in the same
# merged section -- none relies on staying unsplit for a currently-passing merge to keep passing.
_SEMICOLON_CLAUSE_SPLIT_RE = r";\s+(?=`[A-Za-z_][\w.]*\(?\)?`)"
_SENTENCE_GROUP_SPLIT_RE = re.compile(
    r"(?<![Ee]\.[Gg]\.)(?<![Ii]\.[Ee]\.)(?<![Ee]tc\.)(?<=[.!?])\s+(?=[A-Z0-9`\"'])"
    r"|" + _SEMICOLON_CLAUSE_SPLIT_RE
)

# 2026-08-17 -- the precise, deferred fix MT049's own docstring called for: "a correct fix here
# likely needs a more precise signal (e.g., 'does each row/segment have its own distinct
# backtick-quoted subject/token' or similar) rather than a blanket 'always split markdown tables'
# rule." Real markdown table structure (a header row immediately followed by a genuine
# `|---|---|`-shaped separator row) is exactly that precise signal -- it is what actually
# distinguishes `words/python`'s own real `u0020`/`u0015` (a genuine 8-row `### Files` table,
# each row a distinct fact) from the 3 negative-control cases `_split_excerpt_into_sentence_
# groups`'s own docstring already documents (`barcode/python`'s mid-clause line wrap, `3d/java`'s
# heading-to-bullet `\n`, and -- circularly -- this exact table, which is why MT049 had to leave it
# unresolved rather than treat "contains a `\n`" as the signal). Reuses `_EXAMPLES_TABLE_RE`'s own
# established `^\|.+\|\s*$` row-detection idiom, not a new one.
_MARKDOWN_TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$")
_MARKDOWN_TABLE_SEPARATOR_ROW_RE = re.compile(r"^\s*\|(?:\s*:?-+:?\s*\|)+\s*$")


def _split_excerpt_into_table_aware_groups(excerpt: str) -> "list[str] | None":
    """Detects a genuine markdown table inside `excerpt` -- a header row immediately followed by
    a real `|---|---|`-shaped separator row -- and, if found, returns one group per real data
    row (the header/separator rows themselves carry no distinct fact and are dropped), plus one
    or more groups for any prose before/after the table (recursed through `_split_excerpt_into_
    sentence_groups`, which will find no table there and fall through to its own unchanged
    sentence-based split). Returns `None` when no real table is present, so the caller falls
    through to the existing sentence-based split with zero behavior change for every other
    excerpt shape -- this is strictly additive, not a replacement.

    Deliberately keyed on real table structure (a row immediately followed by a separator row),
    never on a bare `\n` or a bare `|` count alone -- `barcode/python`'s own mid-clause line wrap
    and `3d/java`'s own heading-to-bullet `\n` (`_split_excerpt_into_sentence_groups`'s own
    documented negative controls) contain no such separator row and are completely unaffected.
    """
    lines = (excerpt or "").split("\n")
    table_start = None
    for i in range(len(lines) - 1):
        if _MARKDOWN_TABLE_ROW_RE.match(lines[i]) and _MARKDOWN_TABLE_SEPARATOR_ROW_RE.match(lines[i + 1]):
            table_start = i
            break
    if table_start is None:
        return None
    table_end = table_start + 2
    while table_end < len(lines) and _MARKDOWN_TABLE_ROW_RE.match(lines[table_end]):
        table_end += 1

    groups: list[str] = []
    before = "\n".join(lines[:table_start]).strip()
    if before:
        groups.extend(_split_excerpt_into_sentence_groups(before))
    for row_line in lines[table_start + 2 : table_end]:
        row = row_line.strip()
        if row:
            groups.append(row)
    after = "\n".join(lines[table_end:]).strip()
    if after:
        groups.extend(_split_excerpt_into_sentence_groups(after))
    return groups or None


def _split_excerpt_into_sentence_groups(excerpt: str) -> list[str]:
    r"""Splits a unit's excerpt into sentence-level groups on a `.`/`!`/`?` followed by whitespace
    (a plain space OR an embedded `\n` -- deliberately the SAME rule for both, see below) and then
    a capital letter, digit, backtick, or quote. Deliberately does NOT split on a bare `. `
    followed by a lowercase letter, to avoid cutting mid-sentence on an abbreviation or an inline
    code fragment -- and, for the same reason, does NOT split right after `e.g.`/`i.e.`/`etc.`
    even when what follows is capitalized/backtick/quoted (real, confirmed live: `cells/go`'s own
    `u0014`, "...(e.g. `\"A1\"`, `\"B2\"`) ... (e.g. `[0, 0]`) are not supported", would otherwise
    wrongly split after each `e.g.` purely because a backtick immediately follows -- one bullet
    describing one limitation, not 2 bundled facts). A single-sentence excerpt (the large majority
    of real dispositions) still produces exactly one group, so the caller's per-group check
    degenerates to the pre-existing "any one token, anywhere in the excerpt" behavior, unchanged.

    Requiring sentence-terminal punctuation immediately before the split point -- rather than
    treating every embedded `\n` as an unconditional boundary -- was NOT the first design tried,
    and the first design's failure is worth recording: a bare `\n+` split (this incident's
    original portfolio-sweep pass, MT049/Thirty-Ninth incident) correctly separates `note/
    python`'s own captured `u0020` (each of its 2 embedded `\n`s genuinely IS a distinct-fact
    boundary, confirmed by direct reading) -- but a live portfolio sweep against real disposition
    data immediately surfaced `\n` being used for other, non-fact-boundary purposes that an
    unconditional split wrongly treated as compound: `barcode/python`'s own `u0005` wraps a SINGLE
    sentence mid-clause ("...run from\nthe repository root..." -- lowercase word right after the
    `\n`); `3d/java`'s own `u0010` separates a bold heading fragment ("**Excluded APIs:**") from
    markdown bullet items with `\n-`; `words/python`'s own `u0015` is a markdown table with one
    `\n`-delimited row per line. None of these are a compound bundle of separate facts -- they are
    ordinary source-text line-wrapping/list/table structure -- and the unconditional split wrongly
    fragmented each into multiple sentence-groups, producing real false positives (confirmed by
    direct manual re-reading of all 3 against their real target sections before this fix, not
    assumed). The single unified rule here -- ANY whitespace, `\n` included, only counts as a
    split point when the text immediately before it ends with `.`/`!`/`?` -- fixes this: a
    mid-clause line-wrap, a heading-to-bullet `\n`, and a table-row `\n` never sit after
    terminal punctuation, so none of them split; `u0020`'s own 2 embedded `\n`s each DO sit right
    after a real terminal `.`, so both still correctly split, preserving detection of the real
    captured defect this incident closes.

    Resolved 2026-08-17 (the "known tension" this docstring originally left open): a markdown
    table's own rows ARE now split into per-row groups -- see `_split_excerpt_into_table_aware_
    groups`, checked first, below -- using the precise signal that function's own docstring
    already flagged as the correct fix (real `|header|` + `|---|---|` separator structure), not
    a blanket `\n`/table-shape rule. `words/python`'s own real `u0020` (the exact case this
    tension was left unresolved for) now correctly produces one group per file row.
    """
    table_groups = _split_excerpt_into_table_aware_groups(excerpt)
    if table_groups is not None:
        return table_groups
    groups = [g.strip() for g in _SENTENCE_GROUP_SPLIT_RE.split(excerpt or "") if g.strip()]
    if groups:
        return groups
    stripped = (excerpt or "").strip()
    return [stripped] if stripped else []


def _token_occurs_standalone(token: str, text: str) -> bool:
    r"""True if `token` occurs in `text` (case-insensitive) at a position not embedded inside a
    longer contiguous run of word characters (letters/digits/underscore) on either side --
    generalizes a regex `\b` word-boundary check to punctuation-bearing tokens (paths, env-var
    names) where plain `\b` is unreliable (`_` counts as a word character, so `\b` alone already
    fails to bound `PDF` out of `ASPOSE_NOTE_PDF_USE_SYSTEM_FONTS=1`).

    Used ONLY to decide which sentence GROUP a token structurally belongs to, on the excerpt side
    -- the actual target-section-body match below keeps the pre-existing, deliberately lenient
    plain-substring test unchanged, so this does not tighten any already-tuned behavior. Real
    motivating case: `u0020`'s own generic `PDF` token is a literal substring of its own sibling
    token `ASPOSE_NOTE_PDF_USE_SYSTEM_FONTS=1` -- without this standalone check, `PDF` would be
    (wrongly) considered part of every sentence group, including the one whose only real,
    distinctive fact is the env-var override, defeating the per-group split entirely.
    """
    token_l = token.lower()
    text_l = text.lower()
    if not token_l:
        return False

    def _is_word_char(char: str) -> bool:
        return char.isalnum() or char == "_"

    start = 0
    while True:
        idx = text_l.find(token_l, start)
        if idx == -1:
            return False
        before = text_l[idx - 1] if idx > 0 else ""
        after = text_l[idx + len(token_l)] if idx + len(token_l) < len(text_l) else ""
        if not _is_word_char(before) and not _is_word_char(after):
            return True
        start = idx + 1


def _compound_token_trailing_segment(token: str) -> str:
    """Returns the trailing identifier segment of a compound token (`_is_compound_token`) -- the
    part after its last `.`/`/`, with any trailing `()`/parameter-list punctuation stripped, e.g.
    `Document.NUp` -> `NUp`, `/Catalog/OpenAction` -> `OpenAction`, `pdf.NewTable()` ->
    `NewTable`. Used to recognize a bare sibling token (`NUp`, `OpenAction`, `NewTable`) as a
    real, legitimate short name for a compound token already present in the SAME sentence group,
    rather than an unrelated generic word that merely happens to co-occur -- see
    `check_content_unit_merged_into_target_section`'s own docstring for the real, confirmed
    over-strictness this closes (`pdf/go`'s own real u0010: `NUp`/`Booklet` are the product's own,
    already-used short names for `Document.NUp`/`Document.Booklet`, genuinely present in the real
    candidate text -- a first draft of the compound-preference rule that required only the
    compound form itself wrongly flagged this as a gap; the trailing segment is deliberately the
    LEADING namespace's opposite, since `TextStyle.RTL`'s own distinctive part is likewise its
    trailing `RTL`, not the leading, reused `TextStyle` class name -- confirming this asymmetry is
    consistent across both real cases, not coincidental to one).

    MT052 (Forty-Third incident, 2026-08-18): strips any parenthesized argument list BEFORE
    splitting on `.`/`/` -- a real argument list can itself contain a literal `/`
    (`Document.ValidatePDFA(PDFA1B/2B/3B/1A/2A/3A)`), which a naive split-first approach treats
    as more path separators, computing a garbage trailing segment ("3A" instead of the real,
    intended "ValidatePDFA"). Confirmed live, `pdf/go`'s own real `u0023`."""
    core = re.sub(r"\([^()]*\)", "", token)
    tail = re.split(r"[./]", core)[-1]
    return re.sub(r"[(){}\[\],;:'\"`]+$", "", tail)


def _is_compound_token(token: str) -> bool:
    """True if `token` contains a `.` or `/` AND at least one of its `.`/`/`-separated segments
    starts with a letter -- a dotted/slashed API identifier (`Document.SetOpenAction`,
    `/Catalog/OpenAction`) rather than a bare word (`JavaScript`, `TextStyle`, `OpenAction`
    alone) OR a pure-numeric dotted sequence (`12.3.2.2`, `0.31.2` -- an ISO spec section
    citation or a semver version number, found live during MT052's own portfolio sweep: neither
    is a real, alternate-name-bearing API identifier, and requiring one to appear verbatim is a
    materially different, much stricter claim than this rule was ever meant to make). Used by
    `check_content_unit_merged_into_target_section` (MT052, Forty-Third incident, 2026-08-18) to
    require a sentence-group's own MOST distinctive token to match, not just any of its tokens --
    see that function's own docstring for the real, confirmed defect this closes (a group passing
    on a bare, generic word that also happens to appear elsewhere in the document for an
    unrelated reason, while its own real, distinctive dotted identifier is absent)."""
    if "." not in token and "/" not in token:
        return False
    return any(seg and seg[0].isalpha() for seg in re.split(r"[./]", token))


def _token_matches_body(token: str, body_lower: str) -> bool:
    """True if `token` (case-insensitive) appears in `body_lower`, either literally or -- when
    `token` contains one or more parenthesized argument groups, e.g. `Document.SaveDocx(path)`
    or `Document.LoadFontByName("Calibri", bold, italic)` -- with those groups stripped.

    Found live during MT052's own portfolio sweep, `pdf/go`: many real, genuine disposition
    tokens include an illustrative, made-up argument name/list that is never itself literally
    written in the candidate's own, simpler notation (the real candidate genuinely says
    `Document.SaveDocx`, never `Document.SaveDocx(path)`) -- a pure token-authoring/formatting
    mismatch, not a real content gap; a strict literal-substring test alone would have made the
    new compound-token-preference rule (`check_content_unit_merged_into_target_section`) far too
    strict the moment it ran against real, dense, heavily-parenthesized method-signature tokens
    at portfolio scale. Only argument-list parentheses are stripped, never a token's own real,
    load-bearing prefix like `(*Page)`/`(*Document)` (a Go receiver-type notation) -- both the
    literal form and the paren-stripped form are tried, so a token whose parenthesized part is
    genuinely part of its own real identity (rare, not found live) still matches via the first,
    unmodified check.
    """
    token_l = token.lower()
    if token_l in body_lower:
        return True
    stripped = re.sub(r"\([^()]*\)", "", token).strip(" .")
    return bool(stripped) and stripped.lower() in body_lower


# MT052 (Forty-Third incident, 2026-08-18) -- "Mirrors Aspose.X for Y's `Z`" clauses compare the
# Go candidate's own real capability to the commercial .NET SDK's own API naming convention; `Z`
# names a .NET identifier, never a claim that the Go candidate's own code uses that literal name.
# Confirmed real, evidenced, and portfolio-scoped to pdf/go across 6 real units this incident
# individually verified (u0033/u0065/u0096/u0098/u0099/u0107): every one fails only because its
# mirrors clause's own .NET-only token has no Go-side match, while the unit's real, independent
# Go-side claim (already correctly documented) sits in a sibling sentence/group. Both a
# sentence-initial form ("Mirrors Aspose.PDF for .NET's `X`.") and a mid-sentence form
# ("...mirroring the intent of Aspose.PDF for .NET's `X`, adapted to...") are confirmed live.
_MIRRORS_CLAUSE_START_RE = re.compile(
    r"[Mm]irrors?(?:ing)?\b(?:\s+the\s+intent\s+of)?\s+Aspose\.\w+\s+for\s+[\w.]+"
    r"(?:\s*/\s*[\w.]+)?'s\b"
)


def _strip_trailing_mirrors_clause(group_text: str) -> str:
    """Returns `group_text` with everything from a "Mirrors/mirroring [the intent of]
    Aspose.X for Y's" clause onward removed -- see `_MIRRORS_CLAUSE_START_RE`'s own comment for
    why this text must never be required to match the Go candidate's own content."""
    match = _MIRRORS_CLAUSE_START_RE.search(group_text)
    return group_text[: match.start()] if match else group_text


def _mirrors_clause_only_tokens(excerpt: str, tokens: list[str]) -> set[str]:
    """Returns the subset of `tokens` whose every real, standalone occurrence in `excerpt` falls
    entirely within a mirrors clause (per `_strip_trailing_mirrors_clause`) -- these must be
    excluded from `check_content_unit_merged_into_target_section`'s required-token computation
    BEFORE grouping, so they never leak back in via the "ungrouped tokens become their own
    required group" fallback either. A token with no real occurrence in the excerpt at all
    (already outside this excerpt's own text -- a pre-existing, unrelated edge case) is left
    alone, unaffected by this filter."""
    groups = _split_excerpt_into_sentence_groups(excerpt)
    excluded: set[str] = set()
    for tok in tokens:
        if not _token_occurs_standalone(tok, excerpt):
            continue
        found_outside_mirrors = any(
            _token_occurs_standalone(tok, _strip_trailing_mirrors_clause(group))
            for group in groups
        )
        if not found_outside_mirrors:
            excluded.add(tok)
    return excluded


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

    ALSO (TC-HARDEN-78, MT047/Thirty-Seventh incident, 2026-08-15) catches the free-text SIBLING
    of that same shape: an `excluded` entry whose `excluded_reason`/`classification_basis` names
    a target the structured way -- "the candidate['s own] <section name> ... independently
    states/names/covers ..." -- WITHOUT using `verification.evidence_type ==
    "candidate_section_reference"` at all (`evidence_type` is `"clone_cache_path"` instead,
    since the entry's real verification is against the SOURCE, not the candidate). Real,
    confirmed gap: `font/python`'s own current `content-dispositions.json` has exactly 4 entries
    in this shape (`u0001`, `u0006`, `u0028`, `u0049`), each self-disclosing in its own
    `classification_basis` that this claim is "not tracked as a formal verbatim/reframed merge
    to avoid over-claiming exact wording traceability" -- which also means it was never
    mechanically re-validated. `u0028`'s cited claim ("the candidate's own Key Capabilities intro
    paragraph independently states the same 'variable-font-first' framing") went stale after an
    unrelated MT046 edit deleted that intro paragraph entirely, with zero detection until this
    extension closed the gap. `_normalize_independent_statement_target` strips the free text's
    own trailing descriptive word ("section"/"paragraph"/"bullets"/"intro") to recover the real
    heading name.

    Resolution for this new free-text shape deliberately does NOT reuse the excerpt-word-overlap
    fallback below -- found live this incident, against font/python's own real, current
    candidate: a 50%-of-excerpt-words bar (calibrated for a MERGED unit, where the target section
    is expected to closely restate the excerpt) badly over-fires here, since an "independently
    states" claim's own excerpt is routinely a much longer, differently-structured original
    sentence than the compressed phrase actually echoed in the candidate -- it flagged all 4 real
    entries, including `u0001`/`u0049`, which this incident's own Stage 1 re-verification directly
    confirmed are still genuinely accurate. Instead: extract the free text's own quoted phrase
    (the parenthetical `'...'`/`"..."` span the real authoring convention already uses to name the
    exact restated fact, e.g. `u0001`'s `('zero required third-party runtime dependencies')`) and
    require it, hyphen/whitespace-normalized, to appear as a contiguous substring of the target
    section body -- a stricter, more precise test than word-overlap, matching the real, tighter
    resemblance a genuinely-accurate quoted restatement has to its own claim. Confirmed against
    all 3 of font/python's own real, distinctly-shaped quoted claims: `u0001`'s and `u0049`'s both
    resolve (still present, contiguous, verbatim modulo the hyphen/space difference the original
    source's own compound-word styling introduces); `u0028`'s does not (the phrase is genuinely
    gone). A free-text claim with no quoted phrase at all (e.g. a bare parenthetical list with no
    quote marks) falls back to the same excerpt-word-overlap logic the merge/candidate_section_
    reference paths already use below -- a real, disclosed weaker guarantee for that narrower
    shape, not a silent skip.

    ALSO (MT049, Thirty-Ninth incident, 2026-08-15) closes a real, captured gap in the salient-
    tokens path itself, above and independent of the free-text extension: this check's "at least
    one of the unit's salient_tokens appears in the target section" test was originally evaluated
    against the excerpt as a whole. For a COMPOUND excerpt -- several genuinely distinct sentences/
    facts bundled into one `content_unit`, joined by real sentence breaks (a `.`/`!`/`?` followed
    by whitespace -- a plain space or an embedded `\n`, same rule either way -- and then a capital
    letter; see `_split_excerpt_into_sentence_groups`'s own docstring for why a bare `\n` alone is
    NOT used as the split signal) -- that whole-excerpt test could pass on the strength of ONE
    bundled fact's token surviving into
    the merge while a DIFFERENT bundled fact was silently dropped, with zero detection. Real,
    captured case: `note/python`'s own `u0020` (fixed directly in the candidate as part of this same
    incident, not reproduced here) bundles 3 sentences -- golden-PDF storage/manifest comparison,
    cross-platform stability via ReportLab, and the PDF writer's deterministic-Base-14-fonts-by-
    default behavior with its `ASPOSE_NOTE_PDF_USE_SYSTEM_FONTS=1` override -- under 6 shared
    `salient_tokens`. The prior candidate state carried forward only the first fact; this check
    still passed, because the token `"tests/goldens/pdf/"` (that first fact's own token) legitimately
    matched -- with no way to notice the third fact's own distinctive token
    (`ASPOSE_NOTE_PDF_USE_SYSTEM_FONTS=1`) was never written anywhere in the candidate.

    Fix: `_split_excerpt_into_sentence_groups` splits the excerpt into per-sentence groups (a
    single-sentence excerpt -- the large majority of real dispositions -- still produces exactly
    one group). Each of the unit's `salient_tokens` is assigned to every group it structurally
    occurs in, via `_token_occurs_standalone` (not a plain substring test -- see that helper's own
    docstring for why a generic token like `PDF` must not be credited to a sentence purely because
    it is embedded inside a DIFFERENT, longer sibling token's text there). Any token that occurs in
    none of the groups (e.g. sourced from outside the excerpt's own literal text) is treated as one
    more, whole-excerpt-scoped group, preserving today's behavior for that edge case. The check then
    requires EVERY group that has at least one of its own tokens to have at least one of THOSE
    tokens match somewhere in the target section body -- not just any token from anywhere in the
    excerpt. A single-sentence excerpt collapses to exactly one group, so this is provably identical
    to the pre-existing "any one token, anywhere" behavior for that common case -- the actual body-
    side match test itself (`tok.lower() in body.lower()`) is completely unchanged, so no already-
    tuned single-fact disposition's tolerance for legitimate partial-token-survival paraphrasing is
    affected.

    Deliberately NOT a naive uniform stricter threshold (e.g. "require 50% of tokens to match" for
    every entry): this function's own history above (the leading-20-char-literal-substring fallback
    that had to be loosened after false-positiving on dozens of real, correctly-reframed single-fact
    dispositions) is exactly the failure mode a uniform tightening would risk reintroducing for the
    large majority of simple, single-sentence entries. The per-sentence-group split targets ONLY the
    specific, evidenced defect shape (a compound excerpt silently losing one of its bundled facts)
    without changing behavior for anything else. The `excerpt_words`/`body_words` 50%-overlap
    fallback below (for units with no `salient_tokens` at all) is deliberately left untouched by this
    extension -- it already has its own separately-tuned, looser tolerance for paraphrasing, and no
    live compound-excerpt-with-zero-tokens case has been found to justify the added complexity.

    MT052 (Forty-Third incident, 2026-08-18) adds one more precision fix to the per-group match
    itself: within a group, a match is required from the group's own COMPOUND tokens (`_is_
    compound_token` -- containing `.` or `/`, e.g. `Document.SetOpenAction`, `/Catalog/OpenAction`)
    when the group has at least one; a group with no compound token at all falls back to the
    original "any token" test, unchanged. Real, confirmed defect this closes: `pdf/go`'s own u0093
    Group 2 (`SetOpenAction`/`OpenAction`/`RemoveOpenAction`/`/Catalog/OpenAction`/`Document.
    SetOpenAction`/`GoTo`/`JavaScript`) was passing purely via the bare word `"JavaScript"` --
    which legitimately appears dozens of times elsewhere in the document for unrelated reasons
    (`JavaScriptAction`, `JavaScriptCollection`, a `DateField` JS-format action) -- while its own
    real, distinctive dotted identifiers (`Document.SetOpenAction`, `/Catalog/OpenAction`) never
    appeared anywhere in the candidate. `u0042`'s own RTL sentence shows the identical shape,
    passing via the bare, reused class name `"TextStyle"` instead of its own distinctive `TextStyle.
    RTL`. This is a precise, evidence-derived rule, not an arbitrary length/percentage threshold --
    a percentage-based alternative was worked through by hand against both real cases and rejected
    as needing fragile, edge-case-prone tuning where this compound/bare distinction does not.
    Confirmed to NOT regress the one case that should still pass unchanged: `u0093` Group 1 (the
    genuine JS-collection-storage fact) continues to pass via its own compound token `/Catalog/
    Names/JavaScript`.

    Refined once more, same day, after a live portfolio sweep found a real, confirmed FALSE
    POSITIVE the first draft of this rule introduced: `pdf/go`'s own real u0010
    ("**Imposition** -- `Document.NUp` lays multiple source pages... `Document.Booklet`
    reorders...") merges cleanly into a real candidate sentence using the product's own,
    already-established bare short names ("`NUp` and `Booklet` impose pages onto larger sheets"),
    but a "compound tokens only" rule rejected it, since neither bare name is itself a compound
    token. `_compound_token_trailing_segment` fixes this precisely: a bare sibling token is
    promoted to "strong" (required, alongside the compound tokens) only when it exactly equals
    the TRAILING segment of one of the group's own compound tokens (`NUp` from `Document.NUp`,
    `Booklet` from `Document.Booklet`) -- never a blind substring match, which would have wrongly
    promoted `TextStyle` too (a substring of `TextStyle.RTL`, but its LEADING segment, not the
    trailing one) and silently reintroduced the exact RTL false-negative this whole rule exists to
    close. Confirmed by direct re-run against the full portfolio (both candidate trees) before and
    after this refinement: dropped `pdf/go`'s own real finding count from a first-draft high (many
    false positives on legitimately-compressed Key Capabilities bullets, e.g. u0019's `NewTable`/
    `AddTable` as short names for `pdf.NewTable()`/`(*Page).AddTable(...)`) down to a small,
    individually-triaged set -- see MT052's own retroactive-fix record for the exact remaining
    count and disposition.
    """
    sections = _split_into_sections(readme_text)
    findings: list[dict] = []
    for entry in dispositions:
        disposition = entry.get("disposition")
        verification = entry.get("verification") or {}
        independent_statement_match = None
        independent_statement_source = None
        if disposition in ("merged_verbatim", "merged_reframed"):
            target = entry.get("target_section")
        elif disposition == "excluded" and verification.get("evidence_type") == "candidate_section_reference":
            target = verification.get("evidence_ref")
        elif disposition == "excluded":
            # Searched per-field, not on a concatenated blob: excluded_reason and classification_
            # basis are commonly identical duplicated text in real dispositions (font/python's own
            # real shape) -- concatenating them first and slicing from one match's end would still
            # leave the OTHER field's own leading text (including its own quoted phrase) in the
            # remainder, corrupting the "quotes after the verb" scoping below.
            for candidate_field in (entry.get("excluded_reason") or "", entry.get("classification_basis") or ""):
                independent_statement_match = _CANDIDATE_INDEPENDENT_STATEMENT_RE.search(candidate_field)
                if independent_statement_match:
                    independent_statement_source = candidate_field
                    break
            if not independent_statement_match:
                continue
            target = _normalize_independent_statement_target(independent_statement_match.group("section"))
        else:
            continue
        section_key = "__preamble__" if target in ("Intro", "Project History") else target
        body = sections.get(section_key, "")
        if independent_statement_match is not None:
            # Quoted phrases are only meaningful AFTER the "independently states/names/covers"
            # verb -- a quote earlier in the same sentence (e.g. a quoted label naming the
            # OLD/original claim itself, confirmed live in font/python's own real u0006 entry:
            # `'Business artifacts first' positioning. The candidate's own...`) is not the
            # candidate-restated phrase this check needs to verify.
            quoted = _extract_quoted_phrases(independent_statement_source[independent_statement_match.end():])
            if quoted:
                claim = _normalize_for_contiguous_match(quoted[-1])
                if claim and claim not in _normalize_for_contiguous_match(body):
                    findings.append({
                        "unit_id": entry.get("unit_id"),
                        "target_section": target,
                        "reason": "the quoted phrase this excluded entry claims the candidate's "
                                  f"own '{target}' section independently states no longer "
                                  "appears there (contiguous, hyphen/whitespace-normalized "
                                  "match) -- this free-text claim has gone stale",
                    })
                continue
            # No quoted phrase to anchor on -- fall through to the same excerpt-word-overlap
            # fallback the merge/candidate_section_reference paths use below.
        tokens = entry.get("salient_tokens") or []
        if tokens:
            excerpt_for_mirrors = entry.get("excerpt") or ""
            mirrors_only = _mirrors_clause_only_tokens(excerpt_for_mirrors, tokens)
            if mirrors_only:
                remaining = [t for t in tokens if t not in mirrors_only]
                if not remaining:
                    # The whole excerpt was a pure "mirrors the .NET SDK" comparison with no
                    # independent Go-side claim of its own (real, confirmed case: pdf/go's
                    # u0128) -- nothing here is verifiable or unverifiable, so this unit asserts
                    # nothing that could be wrong; skip it rather than falling through to the
                    # word-overlap fallback, which would test the mirrors clause's own generic
                    # words ("intent", "generator") against the body for a meaningless result.
                    continue
                tokens = remaining
        if tokens:
            body_lower = body.lower()
            # MT049/Thirty-Ninth incident: group tokens by which sentence of the excerpt they
            # structurally belong to, then require EACH group's own tokens to have at least one
            # match in the body -- rather than any token from anywhere in the whole excerpt. A
            # single-sentence excerpt collapses to one group, so this is identical to the old
            # "any token, anywhere" behavior for the common case; see the docstring above for the
            # full defect this closes and why a uniform stricter threshold was rejected instead.
            groups = _split_excerpt_into_sentence_groups(entry.get("excerpt") or "")
            group_tokens: list[list[str]] = []
            grouped: set[str] = set()
            for group in groups:
                local = [tok for tok in tokens if _token_occurs_standalone(tok, group)]
                if local:
                    group_tokens.append(local)
                    grouped.update(local)
            ungrouped = [tok for tok in tokens if tok not in grouped]
            if ungrouped:
                group_tokens.append(ungrouped)
            if not group_tokens:
                group_tokens = [list(tokens)]
            # MT052 (Forty-Third incident): within a group, a compound token (dotted/slashed --
            # `_is_compound_token`) must be the one that matches when the group has any; a group
            # with no compound token at all falls back to the original "any token" test. See the
            # docstring above for the real, confirmed defect (a bare, generic word matching for an
            # unrelated reason while the group's own distinctive identifier never appears).
            def _required_tokens(group: list[str]) -> list[str]:
                compound = [tok for tok in group if _is_compound_token(tok)]
                if not compound:
                    return group
                trailing = {
                    _compound_token_trailing_segment(tok).lower()
                    for tok in compound
                    if _compound_token_trailing_segment(tok)
                }
                strong = list(compound)
                strong.extend(
                    tok for tok in group
                    if tok not in compound and tok.lower() in trailing
                )
                return strong

            missing_groups = [
                g for g in group_tokens
                if not any(_token_matches_body(tok, body_lower) for tok in _required_tokens(g))
            ]
            if missing_groups:
                if len(group_tokens) == 1:
                    reason = ("none of this unit's salient tokens were found in the "
                              f"'{target}' section -- the merge/redundancy claim is not "
                              "traceable to real text")
                else:
                    missing_tokens = sorted({tok for g in missing_groups for tok in _required_tokens(g)})
                    reason = (
                        "this unit's excerpt bundles multiple distinct sentences, and at least "
                        f"one of them (tokens: {', '.join(missing_tokens)}) has no match anywhere "
                        f"in the '{target}' section, even though a DIFFERENT sentence's own "
                        "token(s) did match -- a compound excerpt can partially survive a merge "
                        "while silently dropping one of its bundled facts"
                    )
                findings.append({
                    "unit_id": entry.get("unit_id"),
                    "target_section": target,
                    "reason": reason,
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


# MT052 (Forty-Third incident, 2026-08-18) -- a small, disclosed-incomplete extension to the
# existing `_GENERIC_LABEL_WORDS` stoplist, scoped to `check_content_unit_redundant_claim_
# verifiable` only (never applied to `_GENERIC_LABEL_WORDS`'s own existing consumer,
# `check_diagram_no_mechanism_duplicate_output`, which has its own separately-tuned needs).
# Real, confirmed case this closes: `pdf/go`'s own u0041 ("Add blank pages — append or insert
# blank pages into existing documents at any position") has zero backtick-quoted identifiers and,
# even after this extension, its only remaining "significant" words (`append`/`insert`/`blank`)
# either trivially match elsewhere in the API Reference section for unrelated reasons (table-row
# insertion, list appending) or are too generic to count as real evidence on their own -- proving
# a short, identifier-free bullet cannot be reliably word-overlap-verified against a large
# technical document by stoplist-tuning alone.
_REDUNDANT_CLAIM_EXTRA_GENERIC_WORDS = {"page", "pages", "blank", "existing", "position"}


def check_content_unit_redundant_claim_verifiable(
    dispositions: list[dict], readme_text: str
) -> list[dict]:
    """Heuristic, non-blocking. For an `excluded`/`redundant_with_existing` disposition entry
    with EMPTY `salient_tokens` -- i.e. a claim this codebase's own extraction never found a
    backtick-quoted, CamelCase, dotted, or version-shaped identifier for -- filters the excerpt's
    own 4+-letter words through `_GENERIC_LABEL_WORDS` extended with `_REDUNDANT_CLAIM_EXTRA_
    GENERIC_WORDS` (`page`/`pages`/`blank`/`existing`/`position`, evidence-grounded in this exact
    real case, disclosed-incomplete like every other first-instance stoplist in this module). When
    fewer than 3 genuinely distinctive words remain, emits a named "cannot mechanically verify --
    confirm by hand" finding.

    Deliberately a heuristic, not a hard gate: this cannot itself determine whether the claimed
    redundancy is right or wrong -- a short, identifier-free bullet genuinely CAN be redundant
    (many real, correct dispositions in this exact shape exist across the portfolio) -- it only
    removes the false confidence a silent pass from `check_content_unit_merged_into_target_
    section`'s own word-overlap fallback currently gives such a claim, matching the same "even a
    passing gate proves only its own narrow claim" discipline (Anti-Overclaim rule 2) already
    applied to `check_installation_matches_package_registry`'s own hard-gate-to-heuristic
    downgrade once real evidence showed a stronger claim wasn't earned.

    `readme_text` is accepted (not `body`/`target_section`-scoped) for signature symmetry with
    this module's other content-unit checks and as a hook for a future, stronger version of this
    check -- the current logic is excerpt-only, since an `excluded`/`redundant_with_existing`
    entry has no `target_section` to bound a body-side check against (that is exactly the
    property this heuristic exists to flag as unverifiable, not something it can route around).
    """
    del readme_text  # accepted for signature symmetry; see docstring
    findings: list[dict] = []
    for entry in dispositions:
        if entry.get("disposition") != "excluded":
            continue
        if entry.get("classification") != "redundant_with_existing":
            continue
        if entry.get("salient_tokens"):
            continue
        excerpt = entry.get("excerpt") or ""
        words = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", excerpt)}
        distinctive = words - _GENERIC_LABEL_WORDS - _REDUNDANT_CLAIM_EXTRA_GENERIC_WORDS
        if len(distinctive) < 3:
            findings.append({
                "unit_id": entry.get("unit_id"),
                "reason": "this excluded/redundant_with_existing claim has no backtick-quoted "
                          "identifier and fewer than 3 distinctive words remain after the generic-"
                          "label stoplist -- cannot mechanically verify the claimed redundancy is "
                          "real; confirm by hand before trusting it",
            })
    return findings


def check_content_unit_no_exact_duplicate_merge(dispositions: list[dict]) -> list[dict]:
    """Hard gate. Flags two-plus disposition entries with an identical normalized `excerpt`
    merged into the identical `target_section` -- unambiguous, mechanically decidable
    duplication (the fuzzy near-duplicate case is `check_content_unit_probable_duplicate`'s
    heuristic below, not this hard gate).

    Exempts entries whose `verification.evidence_ref` differs (real, live false positive found
    2026-08-19 composing cells/net: 6 different classes -- ValidationCollection,
    ConditionalFormattingCollection, ListObjectCollection, HyperlinkCollection,
    DefinedNameCollection, ChartCollection -- each genuinely have their own `Count: int`
    property, so their Detailed-Member-Reference excerpts are byte-identical
    ("- Properties: `Count: int`") purely by API-shape coincidence, not lazy duplication; each
    was individually verified against its own real source file. This check's excerpt+section
    key can't see that the surrounding class-heading context makes each occurrence a distinct,
    independently-verified fact, not a repeated one. Different evidence_ref is a reliable proxy
    for "these are independently verified, not copy-pasted" -- true lazy duplication (the same
    disposition copied across unit_ids without doing distinct verification work) still shares
    one evidence_ref and remains caught.
    """
    seen: dict[tuple[str, "str | None"], list] = {}
    evidence_by_key: dict[tuple[str, "str | None"], set] = {}
    for entry in dispositions:
        if entry.get("disposition") not in ("merged_verbatim", "merged_reframed"):
            continue
        key = (
            re.sub(r"\s+", " ", (entry.get("excerpt") or "").strip().lower()),
            entry.get("target_section"),
        )
        seen.setdefault(key, []).append(entry.get("unit_id"))
        evidence_by_key.setdefault(key, set()).add(
            (entry.get("verification") or {}).get("evidence_ref")
        )
    findings: list[dict] = []
    for key, unit_ids in seen.items():
        if len(unit_ids) > 1 and len(evidence_by_key[key]) == 1:
            _excerpt, target = key
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


_IMAGE_MARKDOWN_UNIT_RE = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)\s*$")


def check_image_content_unit_excluded_reason_verified(
    content_units: list[dict], dispositions: list[dict], readme_text: str
) -> list[dict]:
    """Heuristic, non-blocking (MT051, Forty-First incident, 2026-08-16). For every content unit
    whose excerpt is BARE image markdown (`![alt](src)`, the whole excerpt, nothing else) and
    whose disposition is `excluded` via `verification.evidence_type == "candidate_section_
    reference"`, requires the image's own real asset FILENAME to genuinely reappear somewhere
    else in the candidate text before trusting the exclusion.

    Real, confirmed gap this closes: `page/python`'s own `content-dispositions.json`
    (`repo-presenter-regen-full` tree) disposed 3 real, verified-present-on-disk screenshot units
    (`u0014`-`u0016`, the original README's `## Example Results` images) as `excluded` /
    `candidate_section_reference` -> `"Key Capabilities"`, each carrying only generic
    format-name tokens (`XPS`, `PDF`, `PS`, `RGB10`). `check_content_unit_merged_into_target_
    section` genuinely ran its own `candidate_section_reference` verification against these
    exact units and reported clean -- because "XPS"/"PDF"/"PS" are common words that
    legitimately, coincidentally recur throughout Key Capabilities' own unrelated format-
    conversion prose, regardless of whether the specific claimed image is actually duplicated
    anywhere. Generic token/word overlap with a PROSE section can confirm a TEXTUAL fact is
    redundant; it can never confirm a SPECIFIC IMAGE is genuinely duplicated elsewhere -- only
    the image's own real asset reference reappearing (re-embedded, or credited by filename) can.
    All 3 images were, in fact, simply dropped -- the candidate had zero image markdown anywhere
    outside its remote CDN banner badge, and the accompanying `excluded_reason` asserted a
    categorically false premise ("the Template's fixed section list has no image-gallery
    section"), directly contradicted by this exact tree's own `font/python` candidate (5 real
    embedded local images) and by `page/python`'s own sibling `repo-presenter` tree (the same 3
    images, genuinely restored under `## Additional Examples` -> `### Example Results`).

    Deliberately heuristic, not a hard gate: precision is proven against exactly one real
    positive case (this incident's own `page/python` regen-full u0014-u0016, correctly flagged)
    and one real negative control (`page/python`'s OTHER, `repo-presenter` tree, whose own
    u0011-u0013 use the identical disposition shape for a GENUINELY true reason -- the same
    images really are embedded elsewhere in that tree's own candidate, and this check correctly
    stays silent there) -- not yet proven at full portfolio scale. Matches filename only (the
    path component after the final `/`), never the full relative path, since a legitimately
    re-embedded image may sit under a different relative-path prefix than its original mention
    (e.g. `readme.resources/mb03.png` re-embedded as `./mb03.png`).
    """
    unit_by_id = {u["unit_id"]: u for u in content_units}
    findings: list[dict] = []
    readme_lower = readme_text.lower()
    for entry in dispositions:
        if entry.get("disposition") != "excluded":
            continue
        verification = entry.get("verification") or {}
        if verification.get("evidence_type") != "candidate_section_reference":
            continue
        uid = entry.get("unit_id")
        excerpt = (entry.get("excerpt") or (unit_by_id.get(uid) or {}).get("excerpt") or "").strip()
        match = _IMAGE_MARKDOWN_UNIT_RE.match(excerpt)
        if not match:
            continue
        src = match.group(1).strip()
        filename = src.rsplit("/", 1)[-1].strip()
        if filename and filename.lower() in readme_lower:
            continue
        findings.append({
            "unit_id": uid,
            "reason": (
                f"this unit's excerpt is a bare image reference ({src!r}), excluded as "
                f"{entry.get('classification')!r} via a candidate_section_reference to "
                f"{verification.get('evidence_ref')!r} -- but the image's own filename "
                f"({filename!r}) never actually reappears anywhere in the candidate text, so "
                "the redundancy claim is unverified. Generic keyword overlap with a prose "
                "section cannot confirm a specific image is genuinely duplicated elsewhere; "
                "only the image's own real asset reference reappearing can."
            ),
        })
    return findings


# ============================================================================================
# Twenty-Fourth incident / mission (2026-08-13): `cells/go`'s real, live upstream README has a
# `## Project Structure` section that is ENTIRELY a fenced directory-tree code block with no
# surrounding prose. `extract_old_readme_content_units` strips ALL fenced code before
# segmenting (by design -- it extracts sentence-level prose facts, not code), so this section
# produced zero content units and was never merged, never excluded-with-reason -- structurally
# invisible to the whole MT030 verify-and-merge pipeline. `check_dropped_content` DOES detect
# the heading as dropped, but that finding is downgraded to non-blocking advisory the moment a
# real content-dispositions.json exists (TC-HARDEN-04), on a theory that's false for any unit
# the extractor never captured in the first place. This section closes that gap with a second,
# parallel extraction mechanism for STRUCTURAL (non-prose) sections, plus a real badge
# semantic-reconciliation mechanism (previously nonexistent) for the sibling "product-specific
# badges get lost or wrongly deduplicated" defect the same mission named as a general problem.
#
# Two new sibling disposition files, agent-authored, same tier as content-dispositions.json:
# structure-dispositions.json, badge-dispositions.json. NOT an extension of content-
# dispositions.json's own schema -- its `classification` enum (narrative/mechanism/branding/
# history/redundant) has no honest value for "a directory tree" or "a badge dedup decision."
# Both key entries on `unit_id` specifically so `check_content_unit_evidence_resolves` -- which
# only ever reads `verification.status/evidence_type/evidence_ref` and echoes back `unit_id` --
# can be reused UNCHANGED as the evidence-resolution gate for both, a real, load-bearing reuse.
# ============================================================================================


_STRUCTURAL_VOCAB_RE = re.compile(
    r"\b(?:project|repo(?:sitory)?|source|directory|folder|codebase)\b(?:\s+\w+){0,2}\s+"
    r"\b(?:structure|layout|organi[sz]ation|tree|map)\b"
    r"|\b(?:structure|layout|organi[sz]ation|tree|map)\b(?:\s+\w+){0,2}\s+"
    r"\b(?:project|repo(?:sitory)?|source|directory|folder|codebase)\b",
    re.IGNORECASE,
)
_TREE_DRAWING_CHARS_RE = re.compile(r"[├└│─]")


def extract_old_readme_structural_units(
    old_readme_text: str, *, min_fenced_dominance: float = 0.6,
    min_fenced_dominance_with_prose: float = 0.85,
) -> list[dict]:
    """Mechanical segmentation of the old upstream README's STRUCTURAL (non-prose) sections into
    checkable units -- the structural counterpart to `extract_old_readme_content_units`, which
    can never see this content by design (it strips fenced code before segmenting).

    Gating test, deliberately content-SHAPE-based rather than a heading-keyword match (the
    mission's own explicit requirement: "Repository Layout"/"Source Layout"/"Project Structure"
    must all be recognized identically, never discarded for using a different heading than a
    template expects). For every H2/H3 heading (`_HEADING_RE`), a section becomes a structural
    unit when (b) fenced code accounts for >= `min_fenced_dominance` (default 60%) of the
    section's real non-blank lines, AND EITHER (a) running `extract_old_readme_content_units`
    against that section's own fenced-code-stripped body yields ZERO real prose units, OR
    (a') the fenced block classifies as `"directory_tree"` (see `_classify_structural_kind`) AND
    dominance is still >= `min_fenced_dominance_with_prose` (default 85%) -- an overwhelmingly
    fenced-dominant, genuine directory-tree diagram whose small residual prose is an incidental
    caption, not an independent fact.

    (a') is deliberately scoped to `directory_tree`-shaped content only, not any fenced-heavy
    section with leftover prose -- checked live, not assumed: relaxing (a) portfolio-wide (any
    section, any kind) against `pdf/cpp`'s own real old README pulled in 7 more sections
    (`"## Opening documents"`, `"## Pages"`, `"## Text extraction"`, etc. -- its own API
    Reference's per-topic code-usage subsections, each just an API snippet plus a one-sentence
    caption) that are NOT directory trees and already have real, separate coverage via
    `extract_old_readme_code_units` (MT047) -- pulling them into `structure-dispositions.json`
    too would have manufactured a duplicate coverage obligation with no matching disposition
    mechanism for it. Narrowing (a') to `kind == "directory_tree"` closes exactly the defect
    class found without expanding scope to content classes already handled elsewhere.

    (a')'s real motivating case (`pdf/cpp`, found live 2026-08-17): the old README's own
    "## Project structure" section is a real directory-tree fenced block (92.3% line dominance)
    followed by ONE trailing architectural sentence ("Public-API bodies under `src/public/`
    call directly into foundation primitives..."). Under the ORIGINAL, stricter gate (any prose
    unit at all disqualifies), that one sentence -- correctly captured by the prose extractor as
    its own real content unit and correctly disposed elsewhere -- silently disqualified the
    ENTIRE section from ALSO becoming a structural unit, so the directory tree itself was never
    captured by any mechanism at all: invisible to both extractors simultaneously, the same root
    shape MT047 already found and fixed for CODE blocks (`extract_old_readme_code_units`, built
    unconditional for exactly this reason) but never fixed here, since a directory tree isn't
    code and needs the structural extractor specifically. A structural unit and a content unit
    are not mutually exclusive -- they live in separate disposition files (`structure-
    dispositions.json` vs. `content-dispositions.json`) with separate id namespaces, so a
    section legitimately contributing both (a dominant tree plus an incidental caption sentence)
    should produce both, not have one silently cancel the other.

    Both `cells/go`'s real "## Installation" section (66.7% dominance, one real, independent,
    substantive prose fact -- "Requires Go 1.18+... zero third-party dependencies", NOT just an
    incidental caption, AND not directory-tree-shaped at all -- excluded on kind alone before
    dominance is even considered) and `pdf/cpp`'s real "## Project structure" (92.3% dominance,
    directory-tree-shaped, one incidental caption) were used to calibrate
    `min_fenced_dominance_with_prose`. 85% sits strictly between the two real, confirmed
    dominance data points (66.7% / 92.3%); like `min_fenced_dominance` itself, this is validated
    against exactly two real products so far -- flagged here, not silently trusted, as needing
    real portfolio-scale confirmation before being treated as a permanent constant, the same
    caveat this plan attaches to every first-instance threshold.

    Returns `[{"unit_id": "s0001", "heading", "heading_level", "kind", "fenced_block_text",
    "dominance_ratio", "claimed_paths"}, ...]` in extraction order -- own `s%04d` id namespace,
    never mixed into `extract_old_readme_content_units`' own `u%04d` array.
    """
    headings = list(_HEADING_RE.finditer(old_readme_text))
    units: list[dict] = []
    for i, match in enumerate(headings):
        heading_text = match.group(2).strip()
        body_start = match.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(old_readme_text)
        body = old_readme_text[body_start:body_end]

        body_lines = [line for line in body.splitlines() if line.strip()]
        if not body_lines:
            continue
        fenced_blocks = _ANY_FENCED_CODE_RE.findall(body)
        if not fenced_blocks:
            continue
        fenced_line_count = sum(
            len([line for line in block.splitlines() if line.strip()]) for block in fenced_blocks
        )
        dominance = fenced_line_count / len(body_lines)
        if dominance < min_fenced_dominance:
            continue

        fenced_block_text = fenced_blocks[0]
        kind = _classify_structural_kind(heading_text, fenced_block_text)

        stripped = _ANY_FENCED_CODE_RE.sub("", body)
        if extract_old_readme_content_units(stripped):
            is_dominant_tree = kind == "directory_tree" and dominance >= min_fenced_dominance_with_prose
            if not is_dominant_tree:
                continue  # real, substantial prose, and either not a directory tree at all or
                # not overwhelmingly fenced-dominant -- the prose extractor's own content unit(s)
                # already cover this section on their own merits

        units.append({
            "unit_id": f"s{len(units) + 1:04d}",
            "heading": heading_text,
            "heading_level": len(match.group(1)),
            "kind": kind,
            "fenced_block_text": fenced_block_text,
            "dominance_ratio": round(dominance, 3),
            "claimed_paths": (
                _parse_directory_tree_paths(fenced_block_text) if kind == "directory_tree" else []
            ),
        })
    return units


def _classify_structural_kind(heading: str, fenced_block_text: str) -> str:
    """Non-gating, best-effort, deliberately an OPEN string (not a closed enum) -- a future kind
    can be added without touching `extract_old_readme_structural_units`' own gate. `"directory_
    tree"` when the fenced block contains real box-drawing characters or the heading matches a
    small structure-vocabulary signal; else `"generic_structural_block"` -- a disclosed "no
    dedicated verifier yet" bucket (covers e.g. a pure command-list section like "## Testing",
    which legitimately also passes the zero-prose-units/high-fenced-dominance gate above but
    isn't a tree needing path verification)."""
    if _TREE_DRAWING_CHARS_RE.search(fenced_block_text) or _STRUCTURAL_VOCAB_RE.search(heading):
        return "directory_tree"
    return "generic_structural_block"


_TREE_LINE_RE = re.compile(r"^((?:[│ ] {3})*)([├└])── (.+)$")


def _parse_directory_tree_paths(fenced_block_text: str) -> list[str]:
    """Best-effort box-drawing directory-tree parser, explicitly disclosed as incomplete -- same
    "presence not proof" honesty `check_named_member_accuracy` already discloses about itself. A
    line it can't confidently parse (doesn't match the expected `(│   )*├── name` / `└── name`
    shape) is silently skipped, never guessed. Feeds ONLY the non-blocking `check_structural_
    unit_tree_paths_plausible` heuristic below, never a hard gate -- a real tree legitimately
    goes stale over time, and a parse gap (e.g. a combined display name like "cell.go / cells.go"
    on one line) must never hard-block a legitimately-updated disposition.
    """
    paths: list[str] = []
    stack: list[str] = []
    for line in fenced_block_text.strip("`").split("\n"):
        match = _TREE_LINE_RE.match(line)
        if not match:
            continue
        prefix, _marker, rest = match.groups()
        name = rest.split("#", 1)[0].strip()
        if not name:
            continue
        depth = len(prefix) // 4
        stack = stack[:depth]
        stack.append(name.rstrip("/"))
        paths.append("/".join(stack))
    return paths


_STRUCTURAL_UNIT_DISPOSITIONS = _CONTENT_UNIT_DISPOSITIONS  # merged_verbatim/merged_reframed/excluded -- reused unchanged, both genuinely fit
_STRUCTURAL_UNIT_VERIFICATION_STATUSES = frozenset({"verified_against_source", "verified_redundant"})


def check_structural_unit_disposition_coverage(
    structural_units: list[dict], dispositions: list[dict]
) -> list[dict]:
    """Hard gate. Direct structural mirror of `check_content_unit_disposition_coverage`: every
    `unit_id` in `structural_units` needs exactly one, well-formed disposition entry (no
    missing/dupe/dangling references); `disposition` is a valid enum value; `merged_*` needs a
    real `target_section`; `excluded` needs a real `excluded_reason` (>=15 chars);
    `verification.status` must be one of `_STRUCTURAL_UNIT_VERIFICATION_STATUSES` (deliberately
    narrower than the prose-side enum -- `not_applicable_category_1`/`verified_by_corroboration`
    are prose-classification-specific and have no honest structural-unit analog) with a non-empty
    `evidence_ref`. Vacuous pass `[]` when `structural_units` is empty -- correctly, since there
    is genuinely nothing to account for.

    `target_section` validity is deliberately NOT restricted to `_CONTENT_UNIT_TARGET_SECTIONS`'
    closed template list -- a structural unit's natural home is very often a genuinely NEW
    section the old README already used (the real `cells/go` case: `## Project Structure`, its
    own real heading, is not one of this skill's template sections at all). A `target_section`
    is valid when it is EITHER an existing template section OR any structural unit's own
    (possibly reframed) `heading` -- open by construction, not a fixed list a future product's
    real heading might not appear on.
    """
    if not structural_units:
        return []
    valid_targets = _CONTENT_UNIT_TARGET_SECTIONS | {u["heading"] for u in structural_units}
    unit_ids = {u["unit_id"] for u in structural_units}
    findings: list[dict] = []
    seen: set[str] = set()
    by_id: dict[str, dict] = {}
    for entry in dispositions:
        uid = entry.get("unit_id")
        if uid in seen:
            findings.append({"unit_id": uid, "reason": "duplicate disposition entry for the same unit_id"})
            continue
        seen.add(uid)
        by_id[uid] = entry
        if uid not in unit_ids:
            findings.append({
                "unit_id": uid,
                "reason": "disposition references a unit_id not present in the current old-README structural extraction",
            })

    for uid in unit_ids:
        entry = by_id.get(uid)
        if entry is None:
            findings.append({"unit_id": uid, "reason": "no disposition entry -- every extracted structural unit needs one"})
            continue
        disposition = entry.get("disposition")
        if disposition not in _STRUCTURAL_UNIT_DISPOSITIONS:
            findings.append({"unit_id": uid, "reason": f"invalid disposition {disposition!r}"})
            continue
        if disposition in ("merged_verbatim", "merged_reframed"):
            target = entry.get("target_section")
            if target not in valid_targets:
                findings.append({
                    "unit_id": uid,
                    "reason": f"merged disposition needs a real target_section, got {target!r}",
                })
        else:  # excluded
            reason_text = (entry.get("excluded_reason") or "").strip()
            if len(reason_text) < 15:
                findings.append({"unit_id": uid, "reason": "excluded disposition needs a real excluded_reason (>=15 chars)"})
        verification = entry.get("verification") or {}
        status = verification.get("status")
        if status not in _STRUCTURAL_UNIT_VERIFICATION_STATUSES:
            findings.append({"unit_id": uid, "reason": f"invalid verification.status {status!r}"})
        elif not verification.get("evidence_ref"):
            findings.append({"unit_id": uid, "reason": "verification needs a non-empty evidence_ref"})
    return findings


def check_structural_unit_merged_into_target_section(
    readme_text: str, dispositions: list[dict]
) -> list[dict]:
    """Hard gate. For every `merged_verbatim`/`merged_reframed` structural disposition, confirms
    the cited `target_section` was genuinely touched with something traceable to this unit.

    For `kind == "directory_tree"` with real `claimed_paths`: requires at least half of the
    claimed paths' basenames (case-insensitive) to appear somewhere in the target section's real
    body -- same "half the significant tokens" idiom `check_content_unit_merged_into_target_
    section`'s own word-overlap fallback already established. For `generic_structural_block` or
    empty `claimed_paths` (a command-list section like "## Testing", or a tree this session's own
    best-effort parser couldn't confidently read): falls back to a disclosed-weaker signal -- the
    target section must contain at least one fenced code block. Weaker on purpose: a command-list
    section's real content IS its commands, and requiring exact-command-text traceability would
    duplicate `check_no_undisclosed_blocking_commands`'s own, more precise job.
    """
    sections = _split_into_sections(readme_text)
    units_by_id: dict[str, dict] = {}
    findings: list[dict] = []
    for entry in dispositions:
        if entry.get("disposition") not in ("merged_verbatim", "merged_reframed"):
            continue
        target = entry.get("target_section")
        body = sections.get(target, "")
        claimed_paths = entry.get("claimed_paths") or []
        if claimed_paths:
            basenames = [p.rsplit("/", 1)[-1].lower() for p in claimed_paths if p]
            hits = sum(1 for b in basenames if b in body.lower())
            if not basenames or hits / len(basenames) < 0.5:
                findings.append({
                    "unit_id": entry.get("unit_id"),
                    "target_section": target,
                    "reason": "fewer than half of this structural unit's claimed paths were "
                              f"found in the '{target}' section -- the merge is not traceable",
                })
        elif not _ANY_FENCED_CODE_RE.search(body):
            findings.append({
                "unit_id": entry.get("unit_id"),
                "target_section": target,
                "reason": f"the '{target}' section contains no fenced code block at all -- a "
                          "merged structural unit with no claimed paths needs at least this "
                          "weaker signal of being genuinely touched",
            })
    return findings


def check_structural_unit_no_exact_duplicate_merge(dispositions: list[dict]) -> list[dict]:
    """Hard gate. Literal structural mirror of `check_content_unit_no_exact_duplicate_merge`,
    keyed on `(normalized heading, target_section)`."""
    seen: dict[tuple[str, "str | None"], list] = {}
    for entry in dispositions:
        if entry.get("disposition") not in ("merged_verbatim", "merged_reframed"):
            continue
        key = (
            re.sub(r"\s+", " ", (entry.get("heading") or "").strip().lower()),
            entry.get("target_section"),
        )
        seen.setdefault(key, []).append(entry.get("unit_id"))
    findings: list[dict] = []
    for (_heading, target), unit_ids in seen.items():
        if len(unit_ids) > 1:
            findings.append({
                "unit_ids": unit_ids,
                "target_section": target,
                "reason": "identical heading merged into the same section under multiple unit_ids -- exact duplicate",
            })
    return findings


def check_structural_unit_tree_paths_plausible(
    structural_units: list[dict], dispositions: list[dict], clone_cache_root: str
) -> list[dict]:
    """Heuristic, non-blocking. For `directory_tree` units with non-empty `claimed_paths`, checks
    each against the real clone cache and surfaces a finding when the resolution ratio is low
    (< 0.7) -- "this tree may be stale, or the best-effort parse may be wrong; confirm by hand."
    Deliberately a heuristic, not a hard gate, matching `check_installation_matches_package_
    registry`'s own downgrade reasoning: a real tree legitimately goes stale as a repo evolves,
    and this must never silently block a legitimately-updated `merged_reframed` disposition just
    because old paths don't resolve 1:1 -- only prompt a human/agent to look.
    """
    units_by_id = {u["unit_id"]: u for u in structural_units}
    root = Path(clone_cache_root)
    findings: list[dict] = []
    for entry in dispositions:
        uid = entry.get("unit_id")
        unit = units_by_id.get(uid)
        if not unit or unit.get("kind") != "directory_tree":
            continue
        paths = unit.get("claimed_paths") or []
        if not paths:
            continue
        resolved = sum(1 for p in paths if (root / p).exists())
        ratio = resolved / len(paths)
        if ratio < 0.7:
            findings.append({
                "unit_id": uid,
                "resolved": resolved,
                "claimed": len(paths),
                "ratio": round(ratio, 2),
                "reason": "fewer than 70% of this tree's claimed paths resolve against the real "
                          "clone cache -- the tree may be stale or the parse may be wrong",
            })
    return findings


_BOX_DRAWING_TREE_CHARS_RE = re.compile(r"[├└│]")  # ├ └ │


def check_project_structure_canonical_tree_format(markdown_text: str) -> list[dict]:
    """Hard gate (2026-08-13, cells/java healing pass). When a `## Project Structure` section
    exists, its fenced tree block must use box-drawing characters (`├──`/`└──`/`│`), matching
    the one real, shipped, already-approved precedent (`cells/go`) -- never the old upstream
    README's own native style (plain indented text, YAML-like nesting, etc.) reproduced
    verbatim. Vacuous pass when no Project Structure section exists -- this section is
    permanently optional, same "vacuously satisfied" precedent as `## Additional Examples`.

    Found live: `cells/java`'s first-drafted Project Structure section reused the old README's
    own plain-indented-text style wholesale (`src/main/java/.../\\n  description text`, no tree
    characters at all) -- producing a visually inconsistent portfolio the moment a second
    product had this section at all, since nothing previously checked *which* visual convention
    a restored directory tree used, only that a fenced code block was present somewhere in the
    section (`check_structural_unit_merged_into_target_section`'s own, deliberately weaker,
    "contains a fenced code block" signal for its own different purpose).

    Mechanically unambiguous (does the text contain box-drawing characters, yes or no), so a
    hard gate, not a heuristic -- unlike the diagram content-purity questions this module also
    checks, "which visual convention" has exactly one correct answer once a precedent exists.
    """
    sections = _split_into_sections(markdown_text)
    section_body = sections.get("Project Structure")
    if section_body is None:
        return []
    fenced_blocks = _ANY_FENCED_CODE_RE.findall(section_body)
    if not fenced_blocks:
        return [{"reason": "Project Structure section has no fenced code block at all"}]
    if not any(_BOX_DRAWING_TREE_CHARS_RE.search(block) for block in fenced_blocks):
        return [{
            "reason": "Project Structure section's fenced tree does not use the canonical "
                      "box-drawing characters (├── / └── / │) "
                      "-- matches neither cells/go's shipped precedent nor any established "
                      "portfolio convention",
        }]
    return []


# ============================================================================================
# Thirty-Seventh incident / MT047 (2026-08-15): the code-example inventory blind spot.
# `extract_old_readme_content_units` strips ALL fenced code before segmenting (by design -- it
# extracts sentence-level prose facts). `extract_old_readme_structural_units` (above) can see
# code, but ONLY when the prose extractor finds NOTHING real in the same section -- its own gate
# is `if extract_old_readme_content_units(stripped): continue` (line ~5245 above), a genuine bug
# found this incident: a section combining a large code block with even one surviving trailing
# prose sentence (`font/python`'s real `## Python API Highlights` -- ~120 lines of code, plus one
# real trailing sentence about the grid-family package) is invisible to BOTH extractors
# simultaneously, by construction, on every product with this shape. `extract_old_readme_code_
# units` below is the fix: UNCONDITIONAL, runs independently of both existing extractors,
# specifically never gated behind whether the prose extractor also has something to say.
# ============================================================================================

_FENCED_CODE_WITH_LANG_RE = re.compile(r"```([\w+-]*)\n?(.*?)```", re.DOTALL)
_CODE_UNIT_SPLIT_THRESHOLD = 15  # non-blank lines; first-iteration threshold, disclosed as a
# considered-not-proven-optimal guess, same posture as every other first-instance numeric
# threshold this module has ever introduced (e.g. extract_old_readme_structural_units's own
# min_fenced_dominance).
_CODE_UNIT_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,4})\s*\(")
_CODE_UNIT_CALL_STOPWORDS = frozenset({
    "if", "for", "while", "print", "with", "def", "class", "return", "elif", "except", "assert",
    "len", "str", "int", "float", "bool", "list", "dict", "set", "tuple", "open", "range", "type",
    "sorted", "enumerate", "isinstance",
})
_CODE_UNIT_BASH_INVOCATION_RE = re.compile(r"^([a-zA-Z][\w-]*)\s+([a-z][\w-]*)")
_CODE_UNIT_BASH_LANGUAGES = frozenset({"bash", "sh", "shell", "console", "zsh"})


def _code_unit_api_call_fingerprint(code_text: str, language: str) -> list[str]:
    """Cheap, deliberately disclosed-incomplete regex scan for `Identifier.method(`/`ClassName(`
    (Python/most languages) or leading CLI-subcommand tokens (bash/shell) -- never a real parser,
    same "presence not proof" honesty `check_named_member_accuracy` already discloses about
    itself. Order-preserving, de-duplicated. For bash: each non-comment, non-blank line's own
    first two whitespace-separated tokens (program + subcommand, e.g. `"aspose-font
    var-instance"`) -- the real, already-established shape of every CLI invocation line in this
    portfolio's old READMEs. For everything else: every `dotted.identifier(` call site, skipping
    a small set of control-flow/builtin keywords that would otherwise pollute the fingerprint
    with noise unrelated to any real API surface.
    """
    fingerprint: list[str] = []
    seen: set[str] = set()
    lang = (language or "").strip().lower()
    if lang in _CODE_UNIT_BASH_LANGUAGES:
        for line in code_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _CODE_UNIT_BASH_INVOCATION_RE.match(stripped)
            if match:
                token = f"{match.group(1)} {match.group(2)}"
                if token not in seen:
                    seen.add(token)
                    fingerprint.append(token)
        return fingerprint
    for match in _CODE_UNIT_CALL_RE.finditer(code_text):
        token = match.group(1)
        if token in _CODE_UNIT_CALL_STOPWORDS or token in seen:
            continue
        seen.add(token)
        fingerprint.append(token)
    return fingerprint


def _code_unit_preceding_prose(old_readme_text: str, block_start: int) -> str:
    """The immediate lead-in line(s) before a fenced code block -- text collected backward from
    `block_start` until a blank line or a heading line, reusing the same "text up to a blank
    line/heading" idiom already proven for `_extract_section_intro_prose` (applied here in the
    opposite direction: backward from the block, not forward from a section start).
    """
    prefix = old_readme_text[:block_start]
    lines = prefix.splitlines()
    collected: list[str] = []
    for line in reversed(lines):
        if not line.strip() or _HEADING_RE.match(line):
            break
        collected.append(line)
    collected.reverse()
    return "\n".join(collected).strip()


def _split_code_block_into_groups(code_text: str) -> list[str]:
    """A fenced code block exceeding `_CODE_UNIT_SPLIT_THRESHOLD` non-blank lines with multiple
    blank-line-separated statement groups is split at those blank-line boundaries -- real,
    visible structural markers already present in the original source's own code (confirmed
    live: `font/python`'s real `## Python API Highlights` block has exactly one blank line per
    distinct demo; its real `## CLI Highlights` block has one blank line per capability
    category), not an invented heuristic. A block at or under the threshold, or one with no
    internal blank-line boundaries at all, stays a single unit.
    """
    non_blank = [line for line in code_text.splitlines() if line.strip()]
    if len(non_blank) <= _CODE_UNIT_SPLIT_THRESHOLD:
        return [code_text]
    groups: list[str] = []
    current: list[str] = []
    for line in code_text.splitlines():
        if not line.strip():
            if current:
                groups.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        groups.append("\n".join(current))
    return groups if len(groups) > 1 else [code_text]


def extract_old_readme_code_units(old_readme_text: str) -> list[dict]:
    """Mechanical segmentation of the old upstream README's fenced CODE into checkable "code
    units" -- the code counterpart to `extract_old_readme_content_units` (prose) and `extract_
    old_readme_structural_units` (non-prose structural blocks, e.g. directory trees). TC-HARDEN-
    74 (MT047/Thirty-Seventh incident, 2026-08-15).

    **Unconditional -- runs independently of both existing extractors, deliberately NOT gated
    behind "does the prose extractor already have something to say about this section."** That
    exact gate is `extract_old_readme_structural_units`'s own `if extract_old_readme_content_
    units(stripped): continue` -- the precise, confirmed-live bug that let `font/python`'s real
    `## Python API Highlights` section (a ~120-line code block covering ~15 distinct capability
    demonstrations, plus one real trailing prose sentence about the grid-family package) fall
    through BOTH extractors simultaneously: too code-heavy for the prose extractor to describe,
    and disqualified from the structural extractor specifically because a small amount of real
    prose survives in the same section. A section with genuinely zero surviving prose (`##
    CLI Highlights`, correctly captured by the structural extractor as a `directory_tree`-
    adjacent `generic_structural_block`) is a narrower, already-handled case; this extractor
    covers the more general, previously entirely uncovered shape.

    For every fenced code block in the whole document (`unit_id` in a new `c%04d` namespace,
    never mixed with `u%04d`/`s%04d`/`b%04d`): `heading_context` (nearest preceding H2/H3 via
    `_HEADING_RE`, `"__preamble__"` if the block precedes any heading), `language` (the fence's
    own language tag, lowercased, `""` if untagged), `code_text`, `preceding_prose` (via
    `_code_unit_preceding_prose`), and `api_call_fingerprint` (via `_code_unit_api_call_
    fingerprint`). A block exceeding `_CODE_UNIT_SPLIT_THRESHOLD` non-blank lines with real
    internal blank-line boundaries is split into sub-units (`c0001a`, `c0001b`, ...) at those
    boundaries via `_split_code_block_into_groups`; a single-group block keeps the bare `c0001`
    id with no letter suffix. Deterministic and order-based (same "survives whitespace-only
    reruns" property `u%04d`/`s%04d` already have) -- running this function twice against
    identical input text produces byte-identical structured output (the machinery-layer
    idempotency proof Stage 8 test 9 / TC-HARDEN-80 depends on).
    """
    headings = list(_HEADING_RE.finditer(old_readme_text))

    def _heading_context(pos: int) -> str:
        context = "__preamble__"
        for heading_match in headings:
            if heading_match.start() <= pos:
                context = heading_match.group(2).strip()
            else:
                break
        return context

    units: list[dict] = []
    block_number = 0
    for block_match in _FENCED_CODE_WITH_LANG_RE.finditer(old_readme_text):
        language = block_match.group(1).strip().lower()
        code_text = block_match.group(2)
        if not code_text.strip():
            continue
        block_number += 1
        heading_context = _heading_context(block_match.start())
        preceding_prose = _code_unit_preceding_prose(old_readme_text, block_match.start())
        groups = [g for g in _split_code_block_into_groups(code_text) if g.strip()]
        multi = len(groups) > 1
        for idx, group_text in enumerate(groups):
            unit_id = f"c{block_number:04d}" + (chr(ord("a") + idx) if multi else "")
            units.append({
                "unit_id": unit_id,
                "heading_context": heading_context,
                "language": language,
                "code_text": group_text,
                "preceding_prose": preceding_prose if idx == 0 else "",
                "api_call_fingerprint": _code_unit_api_call_fingerprint(group_text, language),
            })
    return units


_CODE_UNIT_DISPOSITIONS = frozenset({
    "merged_verbatim", "merged_reframed", "relocated", "excluded", "corrected",
})
_CODE_UNIT_MERGE_DISPOSITIONS = frozenset({
    "merged_verbatim", "merged_reframed", "relocated", "corrected",
})
_CODE_UNIT_VERIFICATION_STATUSES = frozenset({"verified_against_source", "verified_redundant"})


def check_code_example_disposition_coverage(
    code_units: list[dict], dispositions: list[dict]
) -> list[dict]:
    """Hard gate (TC-HARDEN-74, MT047/Thirty-Seventh incident, 2026-08-15). Direct structural
    mirror of `check_structural_unit_disposition_coverage`/`check_content_unit_disposition_
    coverage`, adapted to `code-example-dispositions.json`'s own schema (`unit_id`,
    `heading_context`, `language`, `api_call_fingerprint`, `verification`, `disposition`,
    `target_section`, `excluded_reason` -- Stage 6 item 2's design, no `excerpt`/`salient_tokens`
    fields, since a code unit's checkable identity is its `api_call_fingerprint`, not prose
    tokens). Every `unit_id` `extract_old_readme_code_units` finds needs exactly one well-formed
    disposition entry (no missing/dupe/dangling references); `disposition` is a valid enum value
    (`merged_verbatim`/`merged_reframed`/`relocated`/`corrected`/`excluded`); a merge-shaped
    disposition needs a real `target_section` (the same closed template list `content-
    dispositions.json` already uses -- code examples merge into the same real sections prose
    does, most commonly `Additional Examples`); `excluded` needs a real `excluded_reason` (>=15
    chars); `verification.status` must be one of `_CODE_UNIT_VERIFICATION_STATUSES` with a
    non-empty `evidence_ref`. Vacuous pass when `code_units` is empty -- correctly, since an old
    README with no fenced code at all genuinely has nothing to account for.
    """
    findings: list[dict] = []
    unit_ids = {unit["unit_id"] for unit in code_units}
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
                "reason": "disposition references a unit_id not present in the current old-README code-unit extraction",
            })

    for uid in unit_ids:
        entry = by_id.get(uid)
        if entry is None:
            findings.append({"unit_id": uid, "reason": "no disposition entry -- every extracted code unit needs one"})
            continue
        disposition = entry.get("disposition")
        if disposition not in _CODE_UNIT_DISPOSITIONS:
            findings.append({"unit_id": uid, "reason": f"invalid disposition {disposition!r}"})
            continue
        if disposition in _CODE_UNIT_MERGE_DISPOSITIONS:
            target = entry.get("target_section")
            if target not in _CONTENT_UNIT_TARGET_SECTIONS:
                findings.append({
                    "unit_id": uid,
                    "reason": f"merged/relocated/corrected disposition needs a real target_section, got {target!r}",
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
        if status not in _CODE_UNIT_VERIFICATION_STATUSES:
            findings.append({"unit_id": uid, "reason": f"invalid verification.status {status!r}"})
        elif not verification.get("evidence_ref"):
            findings.append({"unit_id": uid, "reason": "verification needs a non-empty evidence_ref"})
    return findings


def check_code_example_no_exact_duplicate_merge(dispositions: list[dict]) -> list[dict]:
    """Hard gate (TC-HARDEN-74). Mirrors `check_content_unit_no_exact_duplicate_merge`/`check_
    structural_unit_no_exact_duplicate_merge`, adapted to `code-example-dispositions.json`'s own
    schema -- which has no `excerpt` field (Stage 6 item 2's disclosed shape), so duplication is
    decided on the normalized `api_call_fingerprint` tuple instead of excerpt text. Two merged/
    relocated/corrected entries claiming the identical fingerprint into the identical
    `target_section` is unambiguous, mechanically decidable duplication; an entry with an empty
    fingerprint is never flagged here (nothing checkable to compare).

    Exempts entries whose `verification.evidence_ref` differs -- the same, deliberately narrow
    proxy `check_content_unit_no_exact_duplicate_merge` already uses for its own identical-text
    false positive (2026-08-19, cells/net). Real analogous case found composing `font/python`
    (2026-08-20, TC-PC-FONT-PYTHON): two code units under "Export Live and Static Variable Web
    Bundles" both call `WebFontBuilder.build(...)` -- the mechanical, deliberately-incomplete
    `_code_unit_api_call_fingerprint` regex (dotted-call sites only) produces the identical
    single-item fingerprint `["WebFontBuilder.build"]` for both, even though the two calls
    demonstrate genuinely different, independently-verified behavior (`variable_mode="live"`
    vs. `variable_mode="static", stat_policy="static"` -- the static path's STAT-policy handling
    is independently backed by `ttf/tables/stat.py`'s `normalize_static_stat_policy`, a real,
    distinct source dependency the live path never touches). Same asymmetry as the content-unit
    case: true lazy duplication (one disposition copied across unit_ids without distinct
    verification) still shares one evidence_ref and remains caught.
    """
    seen: dict[tuple, list] = {}
    evidence_by_key: dict[tuple, set] = {}
    for entry in dispositions:
        if entry.get("disposition") not in _CODE_UNIT_MERGE_DISPOSITIONS:
            continue
        fingerprint = tuple(entry.get("api_call_fingerprint") or [])
        if not fingerprint:
            continue
        key = (fingerprint, entry.get("target_section"))
        seen.setdefault(key, []).append(entry.get("unit_id"))
        evidence_by_key.setdefault(key, set()).add(
            (entry.get("verification") or {}).get("evidence_ref")
        )
    findings: list[dict] = []
    for key, unit_ids in seen.items():
        if len(unit_ids) > 1 and len(evidence_by_key[key]) == 1:
            fingerprint, target = key
            findings.append({
                "unit_ids": unit_ids,
                "target_section": target,
                "fingerprint": list(fingerprint),
                "reason": "identical api_call_fingerprint merged into the same section under "
                          "multiple unit_ids -- exact duplicate",
            })
    return findings


def _candidate_code_fingerprint(readme_text: str) -> set[str]:
    """The candidate's own whole-document API-call fingerprint -- every fenced code block's
    fingerprint, unioned. Whole-document scope is a deliberate, disclosed choice (not scoped to
    one target section): a capability's surviving demonstration can legitimately land in a
    different, still-genuine section than the disposition's own `target_section` guess (e.g. a
    Quick Start snippet also satisfying an Additional-Examples-targeted claim), and this
    check's job is "did the real capability survive somewhere," not "did it survive in exactly
    the predicted spot."
    """
    fingerprint: set[str] = set()
    for block_match in _FENCED_CODE_WITH_LANG_RE.finditer(readme_text):
        fingerprint.update(_code_unit_api_call_fingerprint(block_match.group(2), block_match.group(1)))
    return fingerprint


def check_code_example_api_coverage_survives(readme_text: str, dispositions: list[dict]) -> list[dict]:
    """Hard gate (TC-HARDEN-75, MT047/Thirty-Seventh incident, 2026-08-15). The direct,
    mechanical fix for the `FontSubsetter`-class of defect this incident's own audit found:
    `font/python`'s real old README demonstrated `FontSubsetter.subset_for_web_with_coverage`,
    `font.preview_naming_policy(...)`, `variable_mode="live"`/`"static"` export, and
    `legacy_family_name`/`typographic_family_name` naming overrides -- none of which had any
    working code anywhere in the candidate, while the section that once demonstrated them was
    disposed `excluded` on a bare "covered elsewhere" theory nothing ever mechanically confirmed.

    For every code unit disposed `merged_verbatim`/`merged_reframed`/`relocated`/`corrected`
    (claiming its real capability survives somewhere in the candidate) with a non-empty
    `api_call_fingerprint`, requires at least half (the same word-overlap threshold idiom
    `check_content_unit_merged_into_target_section` already established) of the unit's own
    fingerprinted calls to appear somewhere in the candidate's real code (`_candidate_code_
    fingerprint`, whole-document scope). A unit whose claimed survival doesn't actually resolve
    is a hard-gate failure -- this is what would have caught the `FontSubsetter` gap
    mechanically, before any human audit was needed. An `excluded` entry is never checked here
    (it claims nothing survives); an entry with an empty fingerprint (e.g. a pure setup/import
    line with no real API call of its own) is skipped -- nothing checkable to verify.
    """
    candidate_fingerprint = _candidate_code_fingerprint(readme_text)
    findings: list[dict] = []
    for entry in dispositions:
        if entry.get("disposition") not in _CODE_UNIT_MERGE_DISPOSITIONS:
            continue
        fingerprint = entry.get("api_call_fingerprint") or []
        if not fingerprint:
            continue
        survived = [call for call in fingerprint if call in candidate_fingerprint]
        if len(survived) / len(fingerprint) < 0.5:
            findings.append({
                "unit_id": entry.get("unit_id"),
                "target_section": entry.get("target_section"),
                "fingerprint": fingerprint,
                "survived": survived,
                "reason": "fewer than half of this code unit's fingerprinted API calls appear "
                          "anywhere in the candidate's own code blocks -- the claimed survival "
                          "does not actually resolve",
            })
    return findings


_NARROW_METHOD_CITATION_RE = re.compile(
    r"section'?s\s+`?([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)?)`?\s+(?:note|method|function|constructor)\b"
)


def check_code_example_excluded_reason_citation_too_narrow(
    dispositions: list[dict], readme_text: str
) -> list[dict]:
    """Heuristic (Forty-Second incident, 2026-08-18 -- manual `pdf/go` preservation review).

    Every `excluded` code-example disposition's own reason is expected to cite either (a) a
    broad area (a real Key Capabilities bullet or API Reference *section* name) that genuinely
    covers the unit's whole real capability, or (b) a single specific method/identifier that
    genuinely IS the unit's own capability. A real, confirmed defect found by manual review:
    `pdf/go`'s real `code-example-dispositions.json` reused the identical narrow citation
    "...API Reference detail section's `NewJavaScriptAction` note" across three sibling units
    under `Document JavaScript & open action` whose real fingerprints are genuinely distinct
    capabilities -- `doc.JavaScript()`'s named-script collection (`c0033b`) and
    `doc.SetOpenAction`/`doc.OpenAction` (`c0033c`/`c0033e`) -- neither of which is
    `NewJavaScriptAction` at all. Confirmed live: `SetOpenAction`/`OpenAction`/`RemoveOpenAction`
    are absent from the entire candidate.

    Detects the narrow-citation grammatical shape (`section's XxxYyy note/method/function/
    constructor`) and, when found, requires every call in the unit's own fingerprint to be
    either the cited identifier itself (substring match either direction, since a fingerprint
    entry is often qualified, e.g. `pdf.NewJavaScriptAction` vs. a bare cited
    `NewJavaScriptAction`) or independently present somewhere in the candidate text -- the same
    substring-presence test `check_code_example_api_coverage_survives` already uses for merged
    units, applied here to the one shape of excluded unit whose own justification names
    something specific enough to be checkable.

    A unit whose reason cites a broad area (no possessive-narrowing clause) is never flagged
    here -- that is the normal, legitimate, majority shape and stays entirely out of this
    check's scope, by design, to avoid the unusable false-positive rate a blanket "does the
    fingerprint appear verbatim" test produces against ordinary prose-reframed capability
    descriptions (confirmed directly against this exact product: 103 of ~130 excluded units
    fail a blanket version of this test, the overwhelming majority legitimately -- narrowing to
    only the possessive-citation shape is what keeps this check's precision usable). Spot-checked
    against `slides/java`'s real code-example-dispositions.json (the only other product with the
    file at the time this check was built) with zero matches -- a real, if narrow, negative
    control, not just an assumption of safety.

    Heuristic, not a hard gate -- the possessive-citation pattern is a first-iteration,
    disclosed-narrow signal (one real, confirmed positive instance calibrated it), not proven at
    portfolio scale.
    """
    findings: list[dict] = []
    for entry in dispositions:
        if entry.get("disposition") != "excluded":
            continue
        reason = entry.get("excluded_reason") or ""
        match = _NARROW_METHOD_CITATION_RE.search(reason)
        if not match:
            continue
        cited = match.group(1)
        fingerprint = entry.get("api_call_fingerprint") or []
        uncovered = [
            call for call in fingerprint
            if cited not in call and call not in cited and call not in readme_text
        ]
        if uncovered:
            findings.append({
                "unit_id": entry.get("unit_id"),
                "cited_identifier": cited,
                "uncovered_calls": uncovered,
                "reason": "the excluded_reason cites one specific identifier, but this unit's "
                          "own fingerprint contains other calls neither matching that identifier "
                          "nor appearing anywhere in the candidate -- the narrow citation likely "
                          "does not cover this unit's real capability",
            })
    return findings


_CLI_CATEGORY_COMMENT_RE = re.compile(r"^\s*#\s*(.+?)\s*$")


def _cli_unit_category(code_text: str) -> "str | None":
    """The CLI-category label for a bash code unit -- the leading `# Comment` line's own text,
    if the unit's first line is a comment (the real, established shape of `font/python`'s old
    `## CLI Highlights` block: `# General inspection and conversion`, `# QA tooling`, `# Web
    packaging`, each starting its own blank-line-delimited group, which `_split_code_block_
    into_groups`'s own blank-line splitting already isolates into separate code units). `None`
    when the unit has no such leading comment -- not every bash unit is part of a labeled
    category.
    """
    lines = code_text.splitlines()
    if lines:
        match = _CLI_CATEGORY_COMMENT_RE.match(lines[0])
        if match:
            return match.group(1)
    return None


def check_cli_category_representation(readme_text: str, code_units: list[dict]) -> list[dict]:
    """Heuristic, non-blocking (TC-HARDEN-75, MT047/Thirty-Seventh incident, 2026-08-15). A
    category-level backstop specifically for the CLI-thinness shape `check_code_example_api_
    coverage_survives`'s half-of-fingerprint threshold could in principle miss: a disposition
    could satisfy that 50% bar while an entire real CATEGORY of CLI usage (e.g. `font/python`'s
    real "QA tooling" group) still has zero representation anywhere in the candidate, simply
    because enough OTHER categories' calls happened to survive.

    Groups bash-language code units (`_cli_unit_category`) by their own leading `# Comment`
    label, and flags any category whose combined `api_call_fingerprint` has zero overlap with
    the candidate's own whole-document code fingerprint (`_candidate_code_fingerprint`).
    Vacuous pass when there are no labeled CLI categories in the old README at all.
    """
    categories: dict[str, list[dict]] = {}
    for unit in code_units:
        if (unit.get("language") or "").lower() not in _CODE_UNIT_BASH_LANGUAGES:
            continue
        category = _cli_unit_category(unit.get("code_text") or "")
        if not category:
            continue
        categories.setdefault(category, []).append(unit)
    if not categories:
        return []
    candidate_fingerprint = _candidate_code_fingerprint(readme_text)
    findings: list[dict] = []
    for category, units in categories.items():
        category_fingerprint: set[str] = set()
        for unit in units:
            category_fingerprint.update(unit.get("api_call_fingerprint") or [])
        if category_fingerprint and not (category_fingerprint & candidate_fingerprint):
            findings.append({
                "category": category,
                "unit_ids": [unit["unit_id"] for unit in units],
                "reason": f"CLI category '{category}' from the old README has zero surviving "
                          "invocation anywhere in the candidate's own code blocks",
            })
    return findings


# --- Badge semantic reconciliation -----------------------------------------------------------

_BADGE_INNER_IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)$")


def extract_badges(readme_text: str) -> list[dict]:
    """Parses every badge (`[![alt](image-url)](link-url)`) out of the README's badge row(s)
    into structured records. Scoped to lines containing `_BADGE_ROW_MARKER`, same scoping
    `extract_old_readme_content_units` already uses to exclude badge rows from prose scanning.
    Returns `[{"unit_id": "b0001", "alt_text", "image_url", "link_url", "raw_markdown"}, ...]`
    in extraction order -- own `b%04d` namespace. Badge-row ORDER shifts more readily between an
    old and new README than prose-paragraph order does (badges get reordered/added/removed
    casually) -- this id scheme is stable across whitespace-only reruns, same as `u%04d`/`s%04d`,
    but NOT across a genuine reordering, worth restating explicitly here since that's likelier in
    practice for badges than for prose.
    """
    badges: list[dict] = []
    for line in readme_text.splitlines():
        if _BADGE_ROW_MARKER not in line:
            continue
        # The required product banner (`[![alt](banner-readme.png)](homepage)`, MT026/TC-HARDEN-27)
        # also matches `_BADGE_ROW_MARKER` but is a distinct, already-governed piece of content,
        # never a semantic badge (CI/license/etc.) -- excluding it here is a precision fix, not
        # load-bearing (it never matches any real `_BADGE_CATEGORY_RULES` category on its own
        # merits, so leaving it in would be harmless, just conceptually imprecise).
        if _BANNER_LINE_RE.match(line) or _LINKED_BANNER_LINE_RE.match(line):
            continue
        for anchor_text, link_url in _MD_LINK_RE.findall(line):
            inner = _BADGE_INNER_IMAGE_RE.match(anchor_text)
            if not inner:
                continue
            alt_text, image_url = inner.groups()
            badges.append({
                "unit_id": f"b{len(badges) + 1:04d}",
                "alt_text": alt_text,
                "image_url": image_url,
                "link_url": link_url,
                "raw_markdown": f"[![{alt_text}]({image_url})]({link_url})",
            })
    return badges


# Checked in this exact order -- most-specific/unambiguous signals first, most-generic last.
# "language_version" is deliberately checked before "package_version" so a real "Go Version"
# badge doesn't collide with the bare `\bversion\b` fallback package_version also carries (found
# live while validating this table against the real cells/go badge set).
_BADGE_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("license", (r"\blicense\b", r"/license[-/]", r"opensource\.org/licenses")),
    ("ci_build_status", (r"\b(?:build|ci)\b", r"\btests?\b", r"\bworkflow\b",
                          r"/actions/workflows/", r"travis-ci|circleci|appveyor")),
    ("coverage", (r"\bcoverage\b", r"codecov|coveralls")),
    ("contributor_count", (r"\bcontributors?\b", r"/contributors")),
    ("download_stats", (r"\bdownloads?\b",)),
    # 2026-08-14: widened after a real, portfolio-wide false positive -- this portfolio's own
    # standard Python-compat badge (shields.io's `/pypi/pyversions/{pkg}.svg`) uses alt text
    # "Python" or "Python versions" (plural), neither of which matched the original
    # singular-"version"-only text pattern; falling through all the way to link_url then
    # matched `package_version`'s bare `pypi\.org` catch-all, making `check_no_duplicate_
    # badges_in_candidate` misfire on every Python product pairing this badge with a real,
    # distinct PyPI-version badge (confirmed live: cells/python, email/python, words/python,
    # slides/python all share this exact shape). The `/pypi/pyversions/` image-URL segment is
    # a mechanically real, shields.io-specific signal for this exact badge type, checked before
    # `image_url`/`link_url` ever reach `package_version`'s broader `pypi\.org` match.
    # "c%2b%2b" (2026-08-14, MT042/TC-HARDEN-58): found live -- 2 real, currently-shipped C++
    # products (email/cpp, slides/cpp) have a real static "C++ 17"/"C++20" language-version
    # badge (`/badge/C%2B%2B-{version}-...`) that fell through this list entirely and classified
    # "unknown", the moment check_badge_row_meets_verified_floor was first run against real
    # content -- confirmed the classifier gap, not a genuine content gap in either product.
    ("language_version", (r"\b(?:go|python|java|rust|node|php|ruby)\s*versions?\b",
                           r"/badge/(?:go|python|java|rust|c%2b%2b)-", r"/pypi/pyversions/")),
    ("language_package_reference", (r"\breference\b", r"pkg\.go\.dev", r"godoc\.org", r"docs\.rs")),
    ("docs_link", (r"\bdocs?\b|\bdocumentation\b",)),
    ("package_version", (r"\bpackage\s*version\b", r"nuget\.org|pypi\.org|maven-central|crates\.io", r"\bversion\b")),
]


def classify_badge(badge: dict) -> dict:
    """Best-effort, OPEN-STRING category classifier (never a closed enum an unrecognized badge
    gets force-fit into -- returns `"unknown"` instead). Checks `alt_text`, then `image_url`,
    then `link_url` against `_BADGE_CATEGORY_RULES` in order; the first category with any
    matching pattern wins. Returns `{"category", "matched_signal", "matched_field"}`.
    """
    for field, text in (("alt_text", badge.get("alt_text", "")),
                        ("image_url", badge.get("image_url", "")),
                        ("link_url", badge.get("link_url", ""))):
        for category, patterns in _BADGE_CATEGORY_RULES:
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return {"category": category, "matched_signal": pattern, "matched_field": field}
    return {"category": "unknown", "matched_signal": None, "matched_field": None}


_STATIC_SHIELDS_BADGE_RE = re.compile(r"img\.shields\.io/badge/", re.IGNORECASE)
_INHERENTLY_DYNAMIC_BADGE_CATEGORIES = frozenset({
    "ci_build_status", "coverage", "download_stats", "contributor_count",
})
# Lower rank = more trustworthy; used by reconcile_badges' "fewer red flags wins" tie-break.
_BADGE_TARGET_KIND_RANK = {
    "local_file_exists": 0, "live_verified_reachable": 0,
    "unverified": 1,
    "static_badge_claims_dynamic_fact": 2,
    "placeholder": 3, "local_file_missing": 3, "live_verified_unreachable": 3,
}


def verify_badge_target(
    badge: dict, category: str, clone_cache_root: str,
    *, live_check: "Callable[[str], bool] | None" = None,
) -> dict:
    """Tiered badge-target verification, deliberately network-cautious by default -- matching
    `_detect_homepage_link`'s own established caution about live-HTTP cost on every run.

    Tier 0 (free, certain): `link_url == "#"` is a structural placeholder incapable of linking
    anywhere real (confirmed real instance: `cells/go`'s own "Tests" badge). A relative
    `link_url` resolves against the clone cache with zero network cost, same technique as
    `_detect_license_file`.

    Tier 1 (free, mechanically real, not a guess): shields.io's own URL grammar distinguishes a
    STATIC, hand-authored badge (`/badge/{label}-{message}-{color}`) from a DYNAMIC, live-queried
    one (`/github/...`, `/pypi/...`, `/maven-central/...`). Validated against 12 real portfolio
    READMEs during this mechanism's design, not just one product's case. When a badge's category
    is inherently dynamic (CI/coverage/downloads/contributors) but its image URL has the static
    shape, that is a real, mechanically-decidable fact -- a static image literally cannot encode
    a live status -- not a guess; correctly leaves legitimately-static categories (license,
    language version) alone.

    Tier 2 (opt-in, off by default): a pluggable `live_check` callable, mirroring `verify-
    examples`'s own `configure(verification_runner=...)` precedent. Never claims a check that
    didn't run -- `target_kind` stays `"unverified"` when `live_check` is `None` (every current
    call site).
    """
    link_url = badge.get("link_url", "")
    image_url = badge.get("image_url", "")
    if link_url == "#":
        return {"target_kind": "placeholder",
                "detail": "link target is '#' -- a same-page anchor with no real destination"}
    if not re.match(r"^https?://", link_url):
        exists = (Path(clone_cache_root) / link_url).is_file()
        return {"target_kind": "local_file_exists" if exists else "local_file_missing"}
    if category in _INHERENTLY_DYNAMIC_BADGE_CATEGORIES and _STATIC_SHIELDS_BADGE_RE.search(image_url):
        return {
            "target_kind": "static_badge_claims_dynamic_fact",
            "detail": f"category {category!r} implies a live status, but the image URL uses "
                      "shields.io's static /badge/ path, which cannot encode one",
        }
    if live_check is not None:
        return {"target_kind": "live_verified_reachable" if live_check(link_url) else "live_verified_unreachable"}
    return {"target_kind": "unverified"}


def _same_real_world_target(a: dict, b: dict) -> bool:
    """Deduplication must compare MEANING and TARGETS, never label/alt-text similarity (the
    mission's own explicit requirement) -- the real License-badge case ("License" vs.
    "License: MIT") pairs correctly here on shared link_url despite different wording, which a
    text-similarity comparison would either miss or false-positive on depending on threshold."""
    def norm(url: str) -> str:
        return (url or "").strip().rstrip("/").lower()
    return bool(norm(a.get("link_url"))) and norm(a.get("link_url")) == norm(b.get("link_url"))


def reconcile_badges(old_badges: list[dict], new_badges: list[dict], clone_cache_root: str) -> dict:
    """Recommends, never silently applies, a duplicate/keep decision for every old badge that
    genuinely shares category + real-world target with a new badge. Returns `{"duplicate_pairs":
    [{"old_unit_id", "new_unit_id", "category", "keep"}, ...], "old_only": [...badges...]}` --
    `old_only` badges have no real duplicate in the candidate and are genuine preserve/exclude
    candidates on their own merits, decided by the disposition file, never by this function.

    Priority for `keep`, deterministic and disclosed, never silent: fewer `verify_badge_target`
    red flags wins (`_BADGE_TARGET_KIND_RANK`); a genuine tie prefers the candidate's own form.
    Simplified from this mechanism's original design (which specified a `keep: null` +
    `dedup_ambiguous` finding for a true tie) -- no real tie case has been found in this
    mechanism's own validation data yet, and "prefer the candidate's already-composed form" is
    itself a defensible, disclosed default rather than an unresolved ambiguity; revisit if a real
    tie case with a wrong outcome is ever found.
    """
    used_new: set[str] = set()
    duplicate_pairs: list[dict] = []
    old_only: list[dict] = []
    for old_badge in old_badges:
        old_category = classify_badge(old_badge)["category"]
        match = None
        if old_category != "unknown":
            for new_badge in new_badges:
                if new_badge["unit_id"] in used_new:
                    continue
                if classify_badge(new_badge)["category"] != old_category:
                    continue
                if _same_real_world_target(old_badge, new_badge):
                    match = new_badge
                    break
        if match is None:
            old_only.append(old_badge)
            continue
        used_new.add(match["unit_id"])
        old_rank = _BADGE_TARGET_KIND_RANK.get(
            verify_badge_target(old_badge, old_category, clone_cache_root)["target_kind"], 1
        )
        new_rank = _BADGE_TARGET_KIND_RANK.get(
            verify_badge_target(match, old_category, clone_cache_root)["target_kind"], 1
        )
        keep = old_badge["unit_id"] if old_rank < new_rank else match["unit_id"]
        duplicate_pairs.append({
            "old_unit_id": old_badge["unit_id"], "new_unit_id": match["unit_id"],
            "category": old_category, "keep": keep,
        })
    return {"duplicate_pairs": duplicate_pairs, "old_only": old_only}


_BADGE_DISPOSITION_ACTIONS = frozenset({"preserved", "superseded_by_duplicate", "excluded"})
_BADGE_VERIFICATION_STATUSES = frozenset({"verified_against_source", "verified_redundant"})


def check_badge_disposition_coverage(
    old_badges: list[dict], new_badges: list[dict], dispositions: list[dict]
) -> list[dict]:
    """Hard gate. Structural mirror of `check_structural_unit_disposition_coverage`: every OLD
    badge needs exactly one, well-formed disposition entry (no missing/dupe/dangling); `action`
    is a valid enum value; `excluded` needs a real `excluded_reason` (>=15 chars);
    `superseded_by_duplicate`/`preserved` need `new_badge_unit_id` to reference a real badge in
    the CURRENT new-badge extraction; `verification.status`/`evidence_ref` required for every
    entry (a `preserved`/`superseded_by_duplicate` action's own real evidence is "this badge
    genuinely appears in the candidate," checked mechanically by `check_badge_preserved_or_
    credited_in_candidate` below -- this function only checks the disposition record's own
    internal well-formedness, matching the same division of labor `check_content_unit_
    disposition_coverage`/`check_content_unit_merged_into_target_section` already use).
    Vacuous pass `[]` when `old_badges` is empty.
    """
    if not old_badges:
        return []
    old_ids = {b["unit_id"] for b in old_badges}
    new_ids = {b["unit_id"] for b in new_badges}
    findings: list[dict] = []
    seen: set[str] = set()
    by_id: dict[str, dict] = {}
    for entry in dispositions:
        uid = entry.get("unit_id")
        if uid in seen:
            findings.append({"unit_id": uid, "reason": "duplicate disposition entry for the same unit_id"})
            continue
        seen.add(uid)
        by_id[uid] = entry
        if uid not in old_ids:
            findings.append({
                "unit_id": uid,
                "reason": "disposition references a unit_id not present in the current old-README badge extraction",
            })

    for uid in old_ids:
        entry = by_id.get(uid)
        if entry is None:
            findings.append({"unit_id": uid, "reason": "no disposition entry -- every old badge needs one"})
            continue
        action = entry.get("action")
        if action not in _BADGE_DISPOSITION_ACTIONS:
            findings.append({"unit_id": uid, "reason": f"invalid action {action!r}"})
            continue
        if action == "excluded":
            reason_text = (entry.get("excluded_reason") or "").strip()
            if len(reason_text) < 15:
                findings.append({"unit_id": uid, "reason": "excluded action needs a real excluded_reason (>=15 chars)"})
        else:  # preserved / superseded_by_duplicate
            credited = entry.get("new_badge_unit_id")
            if credited not in new_ids:
                findings.append({
                    "unit_id": uid,
                    "reason": f"new_badge_unit_id {credited!r} does not reference a real badge in the new candidate",
                })
        verification = entry.get("verification") or {}
        status = verification.get("status")
        if status not in _BADGE_VERIFICATION_STATUSES:
            findings.append({"unit_id": uid, "reason": f"invalid verification.status {status!r}"})
        elif not verification.get("evidence_ref"):
            findings.append({"unit_id": uid, "reason": "verification needs a non-empty evidence_ref"})
    return findings


def check_badge_preserved_or_credited_in_candidate(
    new_badges: list[dict], dispositions: list[dict]
) -> list[dict]:
    """Hard gate. For `preserved`/`superseded_by_duplicate` actions, confirms the cited `new_
    badge_unit_id` genuinely shares the disposition's own stated `category` with the real new
    badge -- catches a lazy or wrong "already covered" claim, the same gap `check_content_unit_
    merged_into_target_section`'s own docstring already names for the prose-merge case.
    """
    new_by_id = {b["unit_id"]: b for b in new_badges}
    findings: list[dict] = []
    for entry in dispositions:
        action = entry.get("action")
        if action not in ("preserved", "superseded_by_duplicate"):
            continue
        credited_id = entry.get("new_badge_unit_id")
        new_badge = new_by_id.get(credited_id)
        if new_badge is None:
            continue  # already flagged by check_badge_disposition_coverage
        real_category = classify_badge(new_badge)["category"]
        claimed_category = entry.get("category")
        if claimed_category != real_category:
            findings.append({
                "unit_id": entry.get("unit_id"),
                "new_badge_unit_id": credited_id,
                "reason": f"disposition claims category {claimed_category!r}, but the cited "
                          f"new badge's real category is {real_category!r} -- not genuinely the same badge",
            })
    return findings


def check_badge_probable_duplicate_disposition(dispositions: list[dict]) -> list[dict]:
    """Heuristic, non-blocking. Mirrors `check_content_unit_probable_duplicate`: flags 2+
    dispositions crediting the SAME `new_badge_unit_id` under different `unit_id`s with
    `action != "excluded"` -- likely double-crediting one candidate badge for two old ones."""
    credited: dict[str, list[str]] = {}
    for entry in dispositions:
        if entry.get("action") in ("preserved", "superseded_by_duplicate"):
            credited.setdefault(entry.get("new_badge_unit_id"), []).append(entry.get("unit_id"))
    return [
        {"new_badge_unit_id": new_id, "unit_ids": old_ids,
         "reason": "multiple old badges credited to the same new badge -- confirm this is genuinely one duplicate, not two different facts"}
        for new_id, old_ids in credited.items() if len(old_ids) > 1
    ]


def check_badge_static_claims_dynamic_fact(readme_text: str) -> list[dict]:
    """Heuristic, non-blocking. Runs against the CANDIDATE directly and unconditionally -- a
    NEW-candidate-quality check, same category as `internal_labels`' own established "not gated
    on old-README existence" posture. Flags any candidate badge whose category is inherently
    dynamic but whose image URL has shields.io's static `/badge/` shape (same Tier-1 signal
    `verify_badge_target` already uses, applied here to catch a freshly-COMPOSED static/fake
    badge, not just a carried-forward old one).
    """
    findings = []
    for badge in extract_badges(readme_text):
        category = classify_badge(badge)["category"]
        if category in _INHERENTLY_DYNAMIC_BADGE_CATEGORIES and _STATIC_SHIELDS_BADGE_RE.search(badge["image_url"]):
            findings.append({
                "unit_id": badge["unit_id"], "category": category,
                "reason": f"category {category!r} implies a live status, but this badge's image "
                          "URL uses shields.io's static /badge/ path, which cannot encode one",
            })
    return findings


def check_no_duplicate_badges_in_candidate(readme_text: str) -> list[dict]:
    """Hard gate. Mechanically decidable, independent of disposition-bookkeeping correctness:
    parses the CANDIDATE's own badge row alone and flags any two badges sharing a real (non-
    `"unknown"`) category and the same real-world target (`_same_real_world_target`) -- the
    direct, rendered-output enforcement of the mission's own explicit "must not display duplicate
    badges that communicate the same fact" requirement, complementing (not replacing)
    `check_badge_disposition_coverage`'s bookkeeping-correctness check above -- a disposition
    file can be perfectly well-formed while the actual rendered candidate still shows both badges
    if a `superseded_by_duplicate` claim's suppressed badge was never actually removed from the
    text. Two badges sharing a label/alt-text alone are NOT flagged (the mission's own explicit
    "compare meaning and targets, not labels" rule) -- only a shared category + shared real
    target is unambiguous duplication.
    """
    badges = extract_badges(readme_text)
    findings: list[dict] = []
    for i, a in enumerate(badges):
        cat_a = classify_badge(a)["category"]
        if cat_a == "unknown":
            continue
        for b in badges[i + 1:]:
            if classify_badge(b)["category"] != cat_a:
                continue
            if _same_real_world_target(a, b):
                findings.append({
                    "unit_ids": [a["unit_id"], b["unit_id"]],
                    "category": cat_a,
                    "reason": "two badges in the candidate share the same category and real-"
                              "world target -- the same fact is displayed twice",
                })
    return findings


# ==================================================================================================
# Thirty-Second incident / MT042 (2026-08-14): badge composition has no floor. Trigger: a
# clean-room `cells/typescript` candidate shipped with a single License badge while every other
# real, currently-shipped candidate in the portfolio has 2-5 (a full 30-product survey found
# zero exceptions). The badge mechanism above (extract_badges/classify_badge/reconcile_badges/
# badge-dispositions.json) is entirely RECONCILIATION-scoped -- it exists only to stop a real
# OLD badge from being silently lost or duplicated -- and vacuously passes when the old README
# has zero badges, exactly the state that let this ship undetected. These two functions close
# the COMPOSITION-time question that mechanism was never designed to answer: does this
# candidate's badge row meet the real, verified floor every other product in the portfolio
# already meets. `_detect_available_badges` (readme_refresh_run.py) computes the real,
# per-category availability from data this pipeline already has -- these functions only compare
# the CANDIDATE's own extracted badge categories against it.
# ==================================================================================================

_BADGE_FLOOR_CATEGORIES = frozenset({
    "package_version", "language_version", "ci_build_status", "contributor_count",
})


def check_badge_row_meets_verified_floor(readme_text: str, available_badges: dict) -> list[dict]:
    """Hard gate (TC-HARDEN-58). The real, empirical floor found across all 30 currently-shipped
    candidates, zero exceptions: a License badge whenever a real MIT license file exists, plus
    at least one more badge from ANY of `_BADGE_FLOOR_CATEGORIES` whenever at least one of those
    is genuinely available. Deliberately does NOT mandate a SPECIFIC second category -- 6 of the
    30 real portfolio products show a CI/build badge in that slot instead of Contributors, a
    legitimate, already-precedented editorial choice; this only requires the candidate's badge
    row to contain at least one real badge from the available set, never a particular one.

    Safe as a hard gate (unlike `check_installation_matches_package_registry`'s own heuristic
    downgrade over `data/package_registry.json`'s disclosed unreliability): `contributor_count`
    depends on nothing but a resolvable `repo_full_name` -- no dependence on any data source this
    plan has found independently wrong -- so the floor can always be satisfied by License +
    Contributors alone even when every other category is genuinely unavailable or wrong.

    When even the License+floor combination is unavailable (both categories genuinely
    unavailable per `available_badges`), reports nothing -- there is no real, verified badge to
    require, and this function never fabricates one to force a pass either way.
    """
    findings: list[dict] = []
    categories_present = {classify_badge(b)["category"] for b in extract_badges(readme_text)}

    license_info = available_badges.get("license", {})
    if license_info.get("available") and "license" not in categories_present:
        findings.append({
            "category": "license",
            "reason": "a real, verified MIT license file exists for this product, but the "
                      "candidate's badge row has no badge classified 'license'",
        })

    floor_available = any(
        available_badges.get(cat, {}).get("available") for cat in _BADGE_FLOOR_CATEGORIES
    )
    if floor_available and not (categories_present & _BADGE_FLOOR_CATEGORIES):
        available_here = sorted(
            cat for cat in _BADGE_FLOOR_CATEGORIES if available_badges.get(cat, {}).get("available")
        )
        findings.append({
            "category": None,
            "reason": f"at least one real, verified badge fact is available "
                      f"({', '.join(available_here)}), but the candidate's badge row contains "
                      f"none of {sorted(_BADGE_FLOOR_CATEGORIES)} -- every currently-shipped "
                      f"portfolio candidate has License plus at least one more badge",
        })
    return findings


def check_badge_available_fact_not_shown(readme_text: str, available_badges: dict) -> list[dict]:
    """Heuristic, non-blocking (TC-HARDEN-59). Flags a genuinely available, verified badge
    category the candidate's badge row does NOT reflect -- a prompt, never a mandate, since
    omitting an available category beyond the mandatory floor (above) is a legitimate,
    already-precedented editorial choice across the real portfolio (6 of 30 products show CI/
    build instead of Contributors; several show only 2 of 5 possible categories).
    """
    categories_present = {classify_badge(b)["category"] for b in extract_badges(readme_text)}
    findings: list[dict] = []
    for category, info in available_badges.items():
        if info.get("available") and category not in categories_present:
            findings.append({
                "category": category,
                "reason": f"a real, verified {category!r} fact is available for this product but "
                          f"no badge in this category appears in the candidate's badge row -- "
                          f"consider adding one (not required beyond the mandatory floor)",
                "suggested_alt_text": info.get("alt_text"),
                "suggested_image_url": info.get("image_url"),
            })
    return findings


# ==================================================================================================
# Thirty-First incident / MT041 (2026-08-14): dependency accuracy. Trigger: the generated
# cells/rust README stated "no external runtime or Microsoft Office installation is needed"
# while the product's own Cargo.toml declares 7 real runtime crates -- a same-document
# contradiction against that file's own, correct Intro paragraph. Real dependency data (a
# DependencySnapshot from dependency_extract.py, real manifest parsing) is added to the
# factpack; these functions verify a composed README's own "## Dependencies" section (a new
# _REQUIRED_SECTIONS entry, placed after Installation) and every other dependency-shaped claim
# in the file against that real, structured data.
# ==================================================================================================

_DEPENDENCY_H3_SUBSECTIONS = (
    "Required Package Dependencies", "Optional Dependencies",
    "Native and System Requirements", "Development Dependencies",
)  # title-case, matching check_heading_title_case (Rule 6) -- "and" stays lowercase, same
# convention as the portfolio's existing "Scope and Limitations"/"Documentation & Resources".
_NO_REQUIRED_DEPS_SENTENCE = "No required third-party package dependencies."


_BARE_VERSION_CONSTRAINT_RE = re.compile(r"[<>=~^!]=?\s*\d[\d.]*|\d[\d.]*")


def _extract_h3_subsection(section_text: str, heading: str) -> str:
    match = re.search(
        rf"^###\s+{re.escape(heading)}\s*$(.*?)(?=^###\s|\Z)",
        section_text, re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    return match.group(1) if match else ""


def check_dependency_section_subheadings_present(
    readme_text: str, dependency_snapshot: "dict | None"
) -> list[dict]:
    """Hard gate (readme-refresh-seo-deps-headings-hardening mission, 2026-08-19). The
    "## Dependencies" contract (TC-HARDEN-49-56, MT041, this module's own header comment above)
    mandates 4 real `###` subheadings -- Required Package Dependencies (never omitted, even for
    the verified-zero fixed sentence), Optional Dependencies / Development Dependencies (silent
    omission only when the corresponding snapshot bucket is genuinely empty), Native and System
    Requirements (silent omission only when `native_system` is genuinely empty) -- but nothing
    ever mechanically enforced their PRESENCE until now. Confirmed real, live defect: 3d/net's
    own "## Dependencies" section (composed 2026-08-19, the same day) is two flat sentences with
    ZERO of the four mandated headings -- a documented-but-unchecked contract, not a violated
    one, the same root-cause shape as every other defect this mission fixes.

    Deliberately does not itself verify subheading CONTENT accuracy -- that is the job of the
    existing check_dependency_direct_transitive_confusion/optional_presented_as_required/
    dev_only_presented_as_runtime family. This check only verifies the four headings' presence
    matches what the real DependencySnapshot data says should exist.
    """
    if not dependency_snapshot:
        return []  # check_dependency_snapshot_completeness already reports this as a hard fail
    dep_section = _split_into_sections(readme_text).get("Dependencies", "")
    if not dep_section:
        return []  # check_required_sections already reports a missing ## Dependencies section

    def _has_h3(heading: str) -> bool:
        return bool(re.search(
            rf"^###\s+{re.escape(heading)}\s*$", dep_section, re.MULTILINE | re.IGNORECASE,
        ))

    findings: list[dict] = []
    if not _has_h3("Required Package Dependencies"):
        findings.append({
            "reason": "the Dependencies section has no \"### Required Package Dependencies\" "
                      "heading -- required unconditionally, even when the snapshot's required "
                      "list is empty (in which case it holds only the fixed sentence \"No "
                      "required third-party package dependencies.\"), never a headingless "
                      "flat paragraph",
        })

    for bucket_key, heading in (
        ("optional", "Optional Dependencies"),
        ("native_system", "Native and System Requirements"),
        ("development", "Development Dependencies"),
    ):
        if dependency_snapshot.get(bucket_key) and not _has_h3(heading):
            findings.append({
                "reason": f"the DependencySnapshot's {bucket_key!r} bucket is non-empty but the "
                          f"Dependencies section has no \"### {heading}\" heading for it -- a "
                          f"real, extracted fact is missing from the composed section",
                "bucket": bucket_key,
            })
    return findings


def _bulleted_dependency_names(subsection_text: str) -> list[str]:
    """Extracts every backtick-quoted token from every top-level bullet -- the established
    `` - `name` ... `` convention already used for every Dependencies-section entry composed
    per this incident's template. A real bug found running this against the real, corrected
    cells/rust candidate: a single, natural bullet can legitimately name several related crates
    together (`` - `sha2` 0.10, `base64` 0.22, `getrandom` 0.3 -- hashing and encoding... ``,
    matching this exact portfolio's own already-established Intro-paragraph prose style for
    grouping related dependencies) -- extracting only the FIRST token per bullet silently
    dropped 2 of 3 real names, producing false "not mentioned" findings. Every backtick token
    in a bullet is now treated as a real, named dependency.

    A second real bug, found the same way against real content (2026-08-14, cells/typescript):
    splitting on a literal `.` truncated any dotted dependency name -- an npm-scoped package
    like `@zip.js/zip.js` (a real, current `cells/typescript` dependency) was cut to `@zip` at
    the first dot, silently producing a false `check_dependency_direct_transitive_confusion`
    finding against the real manifest entry. Dots are real, legitimate characters inside a
    dependency name for multiple ecosystems (npm scopes, Go module paths like
    `golang.org/x/crypto`) -- the token is already isolated to backtick content by
    `_ANY_BACKTICK_TOKEN_RE`, so there is no remaining reason to split on `.` at all. Only
    whitespace/`(` (a trailing parenthetical accidentally captured inside the backticks) are
    real truncation signals.

    A third and fourth real bug, found running `check_dependency_development_claim_not_in_
    manifest` against real, already-shipped content across the portfolio (2026-08-17): (3) the
    established bullet template is `` - `name` [`constraint`] -- description `` (a real,
    optional, backtick-wrapped version constraint immediately after the name, e.g. font/python's
    `` `pytest` `>=7.4` `` or slides/java's `` `5.11.4` ``) -- every backtick span in the
    DESCRIPTION half was also being scanned, so pdf/java's `` ... test runner used by the Maven
    `test` phase `` produced a fabricated-looking name, "test", that was never a dependency at
    all. Only the prefix before the first standalone em-dash (`--`, the template's own documented
    separator) is now scanned; a bullet with no em-dash (e.g. `pdf/python`'s bare `` - `build`
    >=1.2 ``) is scanned in full, unchanged. (4) A bare version-constraint token
    (`>=7.4`, `^25.3.3`, or a bare semver like `5.11.4`) is never itself a real dependency name
    -- excluded via `_BARE_VERSION_CONSTRAINT_RE` regardless of which half of the bullet it
    appears in, since no real package name in any ecosystem this module handles starts with a
    comparison operator or is purely digits and dots."""
    names = []
    for bullet in re.findall(r"^-\s+(.+)$", subsection_text, re.MULTILINE):
        name_prefix = bullet.split("—", 1)[0]
        for token in _ANY_BACKTICK_TOKEN_RE.findall(name_prefix):
            candidate = re.split(r"[(\s]", token)[0]
            if candidate and not _BARE_VERSION_CONSTRAINT_RE.fullmatch(candidate):
                names.append(candidate)
    return names


def check_dependency_snapshot_completeness(
    readme_text: str, dependency_snapshot: "dict | None"
) -> list[dict]:
    """Hard gate. If `dependency_snapshot` is missing entirely, or reaches this check with an
    internal-invariant violation (`applicable=False` with no real `not_applicable_reason`, or
    a non-empty `parse_errors` -- both should be structurally impossible per dependency_
    extract.py's own raise-or-empty invariant, checked anyway rather than just trusted), this
    is a hard failure. The composing agent must never fall back to writing an unqualified
    dependency-free claim (or any dependency prose) when the underlying extraction is missing
    or unreliable -- mirrors check_content_unit_disposition_coverage's "absence is never trust
    it" posture, applied to DependencySnapshot instead of content-dispositions.json."""
    if dependency_snapshot is None:
        return [{
            "reason": "no DependencySnapshot data available for this product -- composing the "
                      "Dependencies section (or any dependency claim elsewhere in the README) "
                      "without it is not permitted; fix extraction, never write from memory",
        }]
    if not dependency_snapshot.get("applicable", True) and not dependency_snapshot.get("not_applicable_reason"):
        return [{"reason": "dependency_snapshot has applicable=False but no not_applicable_reason"}]
    if dependency_snapshot.get("parse_errors"):
        return [{
            "reason": f"dependency_snapshot carries non-empty parse_errors: "
                      f"{dependency_snapshot['parse_errors']!r} -- extraction should have "
                      f"raised instead of returning a partially-failed snapshot",
        }]
    return []


# Mission Claims Policy: bans unqualified absolute no-dependency phrasing -- "no external
# dependencies", "dependency-free", etc. -- UNLESS the claim names the exact dependency class
# it excludes in the same clause AND that is actually proven. Deliberately, bare "runtime"
# alone is never an accepted scope qualifier -- this is what makes the mechanism catch the
# real cells/rust sentence ("no external runtime or Microsoft Office installation is needed"):
# it contains "Microsoft Office" (accepted) and "runtime" (bare, rejected), and "external
# runtime" alone doesn't distinguish "no proprietary Aspose runtime" (true, provable) from "no
# dependencies of any kind" (false -- 7 crates exist).
_UNQUALIFIED_DEPENDENCY_CLAIM_PATTERNS = [
    r"\bno external dependenc(?:y|ies)\b",
    r"\bdependency[- ]free\b",
    r"\bno dependenc(?:y|ies) required\b",
    r"\bcompletely standalone\b",
    r"\bzero dependenc(?:y|ies)\b",
    r"\bno dependenc(?:y|ies) (?:of any kind|at all|whatsoever)\b",
    # Real bug found running this against the real, captured cells/rust sentence: "Requires a
    # recent stable Rust toolchain (2021 edition) -- no external runtime or Microsoft Office
    # installation is needed" was never matched, because the original pattern anchored
    # "requires?" directly onto "no" (`requires? no ...`) -- but "Requires" and "no" are nowhere
    # near adjacent in the real sentence (a whole clause about the Rust toolchain sits between
    # them). The real, load-bearing phrase is "no external runtime"/"no external installation"/
    # "no external software" as its own standalone claim, regardless of what verb precedes it.
    r"\bno external (?:runtime|installation|software)\b",
    r"\bself[- ]contained\b(?!\s+(?:example|snippet|sample|version))",
    r"\bno third[- ]party (?:code|software)\b(?!\s+(?:crate|package|library|dependenc))",
]
_UNQUALIFIED_DEPENDENCY_CLAIM_RE = re.compile(
    "|".join(_UNQUALIFIED_DEPENDENCY_CLAIM_PATTERNS), re.IGNORECASE
)
_DEPENDENCY_SCOPE_QUALIFIER_RE = re.compile(
    # Real bug found running this against real content: every generic noun below (crate/
    # package/library) originally had an OPTIONAL qualifying prefix, so the bare word alone
    # -- "This LIBRARY has no external dependencies", "a fully dependency-free CRATE" -- was
    # incorrectly accepted as if it scoped the claim, purely because "library"/"crate" are also
    # the ordinary generic nouns a README uses to refer to the product itself. Every branch
    # below now REQUIRES a real qualifying adjective (third-party/runtime/native/system) --
    # never a bare crate/package/library on its own.
    r"\bthird[- ]party\s+(?:runtime\s+)?crate(?:s)?\b"
    r"|\bruntime\s+crate(?:s)?\b"
    r"|\bthird[- ]party\s+package(?:s)?\b"
    r"|\bthird[- ]party\s+librar(?:y|ies)\b"
    r"|\bnative(?:\s+system)?\s+librar(?:y|ies)\b"
    r"|\bnative\s+binar(?:y|ies)\b"
    r"|\bsystem\s+librar(?:y|ies)\b"
    r"|\bproprietary\s+(?:aspose\s+)?(?:runtime|sdk|dll|engine)\b"
    r"|\bmicrosoft office\b"
    r"|\bcommercial\s+(?:runtime|license|sdk)\b",
    re.IGNORECASE,
)


_DEPENDENCY_CLAUSE_BOUNDARY_RE = re.compile(r"\s+(?:or|and)\s+|[,;]\s*")


def _unqualified_dependency_claim_findings(text: str) -> list[dict]:
    """Two real bugs found running this against the real, captured cells/rust text before
    trusting it, both fixed in place, not worked around:

    1. A blind +/-120-char window could reach across a sentence/section boundary entirely --
       the Intro paragraph's own separate, correct "no proprietary runtime" sentence was
       incorrectly treated as scoping a completely different, later, unscoped claim in
       Installation just because the two sentences happened to sit close together once other
       sections were stripped out of a test fixture. Fixed: the window is now bounded to the
       CURRENT SENTENCE only (nearest ". "/newline before, nearest "."/newline after).

    2. Even within one sentence, a compound claim joined by "or"/"and" can legitimately scope
       ONE of its coordinated clauses while leaving the other unscoped -- the exact real shape
       of "no external runtime or Microsoft Office installation is needed": "Microsoft Office"
       is a real, accepted qualifier, but it scopes only the SECOND clause ("...installation");
       it must never rescue the FIRST, unrelated, unscoped "no external runtime" claim just
       because both live in one sentence. Fixed: within the sentence, the qualifier search is
       further narrowed to the specific clause (split on "or"/"and"/","/";") containing the
       matched claim itself, never the whole sentence.
    """
    findings = []
    for match in _UNQUALIFIED_DEPENDENCY_CLAIM_RE.finditer(text):
        sentence_start = max(text.rfind(". ", 0, match.start()), text.rfind("\n", 0, match.start()))
        win_start = sentence_start + 1 if sentence_start != -1 else 0
        end_candidates = [p for p in (text.find(c, match.end()) for c in ".\n") if p != -1]
        win_end = min(end_candidates) + 1 if end_candidates else len(text)
        sentence = text[win_start:win_end]

        rel_start, rel_end = match.start() - win_start, match.end() - win_start
        cuts = {0, len(sentence)}
        for boundary in _DEPENDENCY_CLAUSE_BOUNDARY_RE.finditer(sentence):
            cuts.add(boundary.start())
            cuts.add(boundary.end())
        cuts = sorted(cuts)
        clause_start = max((c for c in cuts if c <= rel_start), default=0)
        clause_end = min((c for c in cuts if c >= rel_end), default=len(sentence))
        clause = sentence[clause_start:clause_end]

        if _DEPENDENCY_SCOPE_QUALIFIER_RE.search(clause):
            continue
        findings.append({
            "phrase": match.group(0),
            "context": clause.replace("\n", " ").strip(),
            "reason": "unqualified absolute dependency-absence claim -- scope it to a named "
                      "dependency class (e.g. 'no third-party runtime crate dependencies', "
                      "'no native system libraries', 'no proprietary Aspose runtime') and only "
                      "if that scoped claim is actually proven by the DependencySnapshot data, "
                      "or remove the claim",
        })
    return findings


def check_unqualified_dependency_claims(readme_text: str) -> list[dict]:
    """Hard gate (Claims Policy). Real, live, captured-verbatim motivating case: cells/rust's
    Installation sentence "Requires a recent stable Rust toolchain (2021 edition) -- no
    external runtime or Microsoft Office installation is needed" directly contradicts that
    same file's own Intro paragraph, which correctly names 7 real crate dependencies. See
    _DEPENDENCY_SCOPE_QUALIFIER_RE's own comment for exactly why "runtime" alone never
    qualifies as an accepted scope word."""
    return _unqualified_dependency_claim_findings(readme_text)


def check_dependency_section_manifest_corroboration(
    readme_text: str, dependency_snapshot: "dict | None", corroboration: "dict | None"
) -> list[dict]:
    """Heuristic. Every "### Required package dependencies" bullet's package name should
    appear in the real, freshly-parsed manifest (dependency_snapshot) directly; `claims.json`
    corroboration (via `corroboration["manifest_only"/"claims_only"]`) is a real but
    CONFIRMED-NOT-INDEPENDENT secondary signal (dependency_extract.cross_reference_dependency_
    claims: claims.json's dependency claims are a lossy, name-only re-parse of the SAME
    manifest, at a possibly different revision) -- never authoritative on its own, so this
    stays heuristic, mirroring check_diagram_verified_format_claims'/check_installation_
    matches_package_registry's own established "don't hard-gate on a plausibly-unreliable
    secondary source" lesson.

    Flags: (a) a README bullet whose name has zero corresponding entry anywhere in the
    snapshot's required/optional lists (the name isn't real per the manifest at all); (b) a
    real manifest_only name (a real required dependency the manifest has that the README's
    Required subsection never mentions -- a coverage gap, not a fabrication)."""
    if not dependency_snapshot:
        return []
    dep_section = _split_into_sections(readme_text).get("Dependencies", "")
    required_text = _extract_h3_subsection(dep_section, "Required package dependencies")
    readme_names = set(_bulleted_dependency_names(required_text))
    manifest_names = {e["name"] for e in dependency_snapshot.get("required", [])}
    findings = []
    for name in sorted(readme_names - manifest_names):
        findings.append({
            "name": name,
            "reason": "listed under Required package dependencies but not found in the real, "
                      "freshly-parsed manifest's required entries",
        })
    for name in sorted(manifest_names - readme_names):
        findings.append({
            "name": name,
            "reason": "a real, required manifest dependency is not mentioned in the README's "
                      "Required package dependencies subsection",
        })
    if corroboration:
        for name in corroboration.get("claims_only", []):
            if corroboration.get("same_revision") and name in manifest_names:
                continue  # already covered by the manifest-level checks above
    return findings


def check_dependency_direct_transitive_confusion(
    readme_text: str, dependency_snapshot: "dict | None"
) -> list[dict]:
    """Hard gate. dependency_extract.py's own extractors NEVER read a lockfile -- every entry
    in a DependencySnapshot is, by construction, a direct dependency (`is_direct: True`
    invariant). So "direct/transitive confusion" reduces to a mechanical, unambiguous check: a
    Required-section bullet naming a package absent from the snapshot's real `required` list
    entirely is either a fabrication or (the mission's own named risk) a transitive dependency
    someone mistakenly promoted to Required -- either way, this is a hard, name-level mismatch
    against deterministic manifest-parse data, not a judgment call."""
    if not dependency_snapshot:
        return []
    dep_section = _split_into_sections(readme_text).get("Dependencies", "")
    required_text = _extract_h3_subsection(dep_section, "Required package dependencies")
    readme_names = set(_bulleted_dependency_names(required_text))
    manifest_required = {e["name"] for e in dependency_snapshot.get("required", [])}
    return [
        {"name": name, "reason": "not a real, direct required dependency per the manifest -- "
                                  "possibly a transitive dependency incorrectly listed as direct"}
        for name in sorted(readme_names - manifest_required)
    ]


def check_dependency_optional_presented_as_required(
    readme_text: str, dependency_snapshot: "dict | None"
) -> list[dict]:
    """Hard gate: a snapshot entry with category="optional" listed under Required package
    dependencies, or a category="required" entry listed under Optional dependencies -- a pure
    field-vs-section-placement mismatch, mirroring check_content_unit_merged_into_target_
    section's "claim lands where its own data says" shape."""
    if not dependency_snapshot:
        return []
    dep_section = _split_into_sections(readme_text).get("Dependencies", "")
    required_names = set(_bulleted_dependency_names(
        _extract_h3_subsection(dep_section, "Required package dependencies")
    ))
    optional_names = set(_bulleted_dependency_names(
        _extract_h3_subsection(dep_section, "Optional dependencies")
    ))
    findings = []
    for e in dependency_snapshot.get("optional", []):
        if e["name"] in required_names:
            findings.append({"name": e["name"], "reason": "optional per the manifest, but listed under Required"})
    for e in dependency_snapshot.get("required", []):
        if e["name"] in optional_names:
            findings.append({"name": e["name"], "reason": "required per the manifest, but listed under Optional"})
    return findings


def check_dependency_dev_only_presented_as_runtime(
    readme_text: str, dependency_snapshot: "dict | None"
) -> list[dict]:
    """Hard gate: a dev_only=True snapshot entry listed under Required package dependencies
    instead of Development dependencies -- the mission's own named "dev-only dependency
    presented as runtime" risk, made mechanical."""
    if not dependency_snapshot:
        return []
    dep_section = _split_into_sections(readme_text).get("Dependencies", "")
    required_names = set(_bulleted_dependency_names(
        _extract_h3_subsection(dep_section, "Required package dependencies")
    ))
    return [
        {"name": e["name"], "reason": "a development-only dependency per the manifest, but "
                                       "listed under Required package dependencies"}
        for e in dependency_snapshot.get("development", []) if e["name"] in required_names
    ]


def check_dependency_development_claim_not_in_manifest(
    readme_text: str, dependency_snapshot: "dict | None"
) -> list[dict]:
    """Hard gate (2026-08-17, the slides/* portfolio audit). Every real, existing dependency
    check in this module corroborates the "### Required Package Dependencies" subsection against
    the real manifest -- `check_dependency_direct_transitive_confusion` (hard gate: a Required
    claim absent from the manifest entirely), `check_dependency_section_manifest_corroboration`
    (heuristic: both directions), `check_dependency_optional_presented_as_required`/`check_
    dependency_dev_only_presented_as_runtime` (hard gates: wrong-bucket placement). Not one of
    them ever checks whether a claimed "### Development Dependencies" bullet corresponds to any
    real entry in the manifest's own `development` bucket at all -- a real, live-confirmed gap:
    `slides/python`'s real candidate claims `pytest>=7` and `python-pptx>=1.0` as development
    dependencies, and NEITHER is declared anywhere in the real `pyproject.toml` (no `[project.
    optional-dependencies]` table exists at all) nor imported anywhere in the real test suite --
    a fully fabricated dependency claim that passed every other dependency check in this module
    cleanly, precisely because none of them look at this specific bucket/section pairing at all.
    Mirrors `check_dependency_direct_transitive_confusion`'s exact shape and hard-gate severity,
    scoped to the Development side instead of Required -- a name with zero match anywhere in the
    manifest's real `development` entries is exactly as mechanically unambiguous a fabrication as
    the Required-side case that check already treats as a hard gate, not a judgment call."""
    if not dependency_snapshot:
        return []
    dep_section = _split_into_sections(readme_text).get("Dependencies", "")
    development_text = _extract_h3_subsection(dep_section, "Development Dependencies")
    readme_names = set(_bulleted_dependency_names(development_text))
    manifest_names = {e["name"] for e in dependency_snapshot.get("development", [])}
    return [
        {"name": name, "reason": "listed under Development Dependencies but not found anywhere "
                                  "in the real, freshly-parsed manifest's development entries -- "
                                  "possibly a fabricated dependency claim"}
        for name in sorted(readme_names - manifest_names)
    ]


def check_dependency_scope_claim_matches_evidence(
    readme_text: str, dependency_snapshot: "dict | None"
) -> list[dict]:
    """Heuristic (downgraded from an originally-planned hard gate the moment this ran against
    real content -- see readme_refresh_run.py's own wiring comment for the full account).
    Mechanizes the mission's own core "package independence vs. proprietary-runtime
    independence" distinction: a *scoped* claim (one that passed check_unqualified_dependency_
    claims because it named a real dependency class) whose named category has ZERO
    corresponding snapshot entries at all is absence of evidence, not evidence of absence --
    e.g. "no proprietary Aspose runtime" is only a fully verified claim if the snapshot's own
    proprietary_runtime category was actually checked and found empty, not merely never
    populated. Stays heuristic because NO extractor today populates that category at all (no
    per-ecosystem signal exists for "does this crate declare a commercial runtime dependency"),
    so every occurrence of this real, sanctioned phrasing will always be flagged -- a real,
    honest disclosure that the category is unverified, not proof the claim is false."""
    if dependency_snapshot is None:
        return []
    findings = []
    for match in re.finditer(
        r"\bno\s+proprietary\s+(?:aspose\s+)?(?:runtime|sdk|dll|engine)\b", readme_text, re.IGNORECASE,
    ):
        if not dependency_snapshot.get("proprietary_runtime"):
            # An empty list here is honest ("checked, found none") only when the extractor
            # actually inspects for this category -- today's extractors never populate it
            # (no per-ecosystem "does this crate/package embed a commercial runtime" signal
            # exists), so a claim of this shape is always flagged for a human to verify by
            # hand until such a signal is built.
            findings.append({
                "phrase": match.group(0),
                "reason": "claims no proprietary runtime, but no extractor currently verifies "
                          "this category -- confirm by hand before trusting this claim",
            })
    return findings


def check_dependencies_scope_limitations_contradiction(readme_text: str) -> list[dict]:
    """Heuristic, non-blocking. Cross-section correlation between "## Dependencies" and "##
    Scope and Limitations", mirroring check_capability_scope_contradiction's own coarse
    substring-match technique (extended here to the Dependencies/Scope pairing instead of Key
    Capabilities/Scope). Free-prose cross-section correlation, same judgment ceiling as its
    sibling -- a prompt, never an automatic fail."""
    sections = _split_into_sections(readme_text)
    dep_text = sections.get("Dependencies", "")
    scope_match = _SCOPE_LIMITATIONS_SECTION_RE.search(readme_text)
    if not dep_text or not scope_match:
        return []
    dep_bullets = re.findall(r"^-\s+(.+)$", dep_text, re.MULTILINE)
    scope_bullets = re.findall(r"^-\s+(.+)$", scope_match.group(1), re.MULTILINE)
    stub_bullets = [b for b in scope_bullets if _STUB_INDICATOR_RE.search(b)]
    findings = []
    for bullet in dep_bullets:
        tokens = _ANY_BACKTICK_TOKEN_RE.findall(bullet)
        if not tokens:
            continue
        keyword = re.split(r"[.(]", tokens[0])[0]
        if len(keyword) < 4:
            continue
        keyword_re = re.compile(re.escape(keyword), re.IGNORECASE)
        for stub_bullet in stub_bullets:
            if keyword_re.search(stub_bullet):
                findings.append({
                    "dependency_bullet": bullet, "matched_keyword": keyword,
                    "scope_bullet": stub_bullet,
                    "reason": f"'{keyword}' is named in Dependencies, but a Scope and "
                              f"Limitations bullet documents related functionality as "
                              f"not-implemented/stub -- verify these aren't contradictory",
                })
                break
    return findings


def check_dependencies_intro_contradiction(
    readme_text: str, dependency_snapshot: "dict | None"
) -> list[dict]:
    """Hard gate. The exact real cells/rust defect shape: the unheaded Intro paragraph
    correctly, scopedly names real dependencies, while a LATER section (Installation or
    Dependencies) states an unqualified absolute claim that contradicts it -- both sides are
    now mechanically extractable (Intro prose vs. the real DependencySnapshot), unlike check_
    dependencies_scope_limitations_contradiction's two free-prose sections, so this can be a
    hard gate. Fires when the preamble names at least one real snapshot dependency AND any
    section other than the preamble contains an unqualified dependency claim."""
    if not dependency_snapshot or not dependency_snapshot.get("required"):
        return []
    sections = _split_into_sections(readme_text)
    preamble = sections.get("__preamble__", "")
    required_names = {e["name"] for e in dependency_snapshot["required"]}
    preamble_names_mentioned = {
        name for name in required_names
        if re.search(rf"\b{re.escape(name)}\b", preamble, re.IGNORECASE)
    }
    if not preamble_names_mentioned:
        return []
    rest_of_document = readme_text[len(preamble):]
    unqualified_elsewhere = _unqualified_dependency_claim_findings(rest_of_document)
    if not unqualified_elsewhere:
        return []
    return [{
        "preamble_dependencies_named": sorted(preamble_names_mentioned),
        "contradicting_claim": f["phrase"],
        "context": f["context"],
        "reason": "the Intro paragraph correctly names real dependencies, but a later section "
                  "states an unqualified absolute dependency-absence claim -- a same-document "
                  "contradiction",
    } for f in unqualified_elsewhere]


_DEPENDENCY_NAME_AND_VERSION_RE = re.compile(r"`([\w.-]+)`\s*([\^~]?\d+(?:\.\d+){0,2})?")


def check_dependency_version_pin_freshness(
    readme_text: str, dependency_snapshot: "dict | None"
) -> list[dict]:
    """Heuristic, non-blocking: a version number cited in Dependencies-section prose that
    doesn't match the manifest's real current constraint. Manifest ranges (e.g. "^0.4") vs.
    prose-stated versions are routinely, legitimately non-identical (a range vs. a specific
    pinned point), so this stays a prompt, never a block -- mirrors check_installation_
    matches_package_registry's own version-caution lesson.

    A real bug found running this against the real, corrected cells/rust candidate: the
    original version-search scanned the WHOLE bullet for the first digit-looking token, which
    can match a digit embedded in the crate's OWN NAME (e.g. `sha2` contains "2") before ever
    reaching the real version number that follows it -- and a multi-crate bullet (`` `sha2`
    0.10, `base64` 0.22, `getrandom` 0.3 ``) needs each name paired with the version
    IMMEDIATELY following its own backtick token, not a single version borrowed for the whole
    bullet. Fixed via _DEPENDENCY_NAME_AND_VERSION_RE, matching each backtick-quoted name
    together with whatever version-shaped token directly follows it.
    """
    if not dependency_snapshot:
        return []
    dep_section = _split_into_sections(readme_text).get("Dependencies", "")
    required_text = _extract_h3_subsection(dep_section, "Required package dependencies")
    by_name = {e["name"]: e for e in dependency_snapshot.get("required", [])}
    findings = []
    for bullet in re.findall(r"^-\s+(.+)$", required_text, re.MULTILINE):
        for raw_name, version in _DEPENDENCY_NAME_AND_VERSION_RE.findall(bullet):
            name = re.split(r"[.(\s]", raw_name)[0]
            entry = by_name.get(name)
            if not entry or not entry.get("version_constraint") or not version:
                continue
            if version not in (entry["version_constraint"] or ""):
                findings.append({
                    "name": name, "readme_version": version,
                    "manifest_version": entry["version_constraint"],
                    "reason": "the version cited in prose doesn't match the manifest's real "
                              "current constraint -- may be stale, or a legitimate range vs. "
                              "specific-point difference; verify before trusting either",
                })
    return findings


def check_dependency_native_system_scope_limitations_placement(readme_text: str) -> list[dict]:
    """Hard gate: reuses check_scope_limitations_format's already-hard-gated structural
    contract, adding only the cross-section duplication rule (a Native and System Requirements
    bullet duplicated verbatim in Scope and Limitations too) -- mechanical, not a judgment
    call."""
    sections = _split_into_sections(readme_text)
    dep_text = sections.get("Dependencies", "")
    native_text = _extract_h3_subsection(dep_text, "Native and system requirements")
    native_bullets = {
        b.strip() for b in re.findall(r"^-\s+(.+)$", native_text, re.MULTILINE) if len(b.strip()) > 15
    }
    if not native_bullets:
        return []
    scope_match = _SCOPE_LIMITATIONS_SECTION_RE.search(readme_text)
    if not scope_match:
        return []
    scope_bullets = {b.strip() for b in re.findall(r"^-\s+(.+)$", scope_match.group(1), re.MULTILINE)}
    duplicates = native_bullets & scope_bullets
    return [
        {"bullet": b, "reason": "duplicated verbatim in both Dependencies (Native and System "
                                 "Requirements) and Scope and Limitations"}
        for b in sorted(duplicates)
    ]


def check_dependency_disposition_reconciliation(
    content_units: list, dispositions: list, dependency_snapshot: "dict | None"
) -> list[dict]:
    """Hard gate. Extends check_content_unit_disposition_coverage/check_content_unit_evidence_
    resolves: narrows an already-required evidence-presence rule to the dependency-shaped
    subset specifically. Every disposition entry classified "5_dependency_claim" must cite
    real evidence (its evidence_ref must name either the real source_manifest_path or a real
    dependency name from the snapshot) -- never narrative-only evidence for a claim about what
    a manifest says."""
    if not dependency_snapshot:
        return []
    real_names = {
        e["name"]
        for bucket in ("required", "optional", "native_system", "proprietary_runtime", "development")
        for e in dependency_snapshot.get(bucket, [])
    }
    manifest_path = dependency_snapshot.get("source_manifest_path") or ""
    findings = []
    for entry in dispositions:
        if entry.get("classification") != "5_dependency_claim":
            continue
        evidence_ref = (entry.get("verification", {}) or {}).get("evidence_ref") or ""
        cites_manifest = bool(manifest_path) and manifest_path in evidence_ref
        cites_real_name = any(name and name in evidence_ref for name in real_names)
        if not cites_manifest and not cites_real_name:
            findings.append({
                "unit_id": entry.get("unit_id"),
                "reason": "a 5_dependency_claim disposition's evidence_ref must cite the real "
                          "source manifest path or a real dependency name from the snapshot, "
                          "not narrative-only evidence",
            })
    return findings


def build_dependency_verification_matrix(
    dependency_snapshot: "dict | None", readme_text: str, claims: "list | None" = None,
) -> dict:
    """Reviewer-facing, read-only artifact (never gates anything itself -- gating already
    happens via the checks above). One row per DependencySnapshot entry, showing exactly which
    independent signals corroborate it, so a human can see at a glance which crate landed in
    the README on how many signals."""
    dep_section = _split_into_sections(readme_text).get("Dependencies", "")
    required_text = _extract_h3_subsection(dep_section, "Required package dependencies")
    in_section = set(_bulleted_dependency_names(required_text))
    prose_rest = readme_text.replace(dep_section, "", 1)
    claim_names = set()
    for c in (claims or []):
        text = c.get("text", "")
        if text.startswith("Depends on "):
            claim_names.add(text[len("Depends on "):].strip())

    rows = []
    if dependency_snapshot:
        for bucket in ("required", "optional", "native_system", "proprietary_runtime", "development"):
            for e in dependency_snapshot.get(bucket, []):
                name = e["name"]
                in_prose = bool(re.search(rf"\b{re.escape(name)}\b", prose_rest, re.IGNORECASE))
                in_claims = name in claim_names
                score = sum([name in in_section, in_prose, in_claims])
                rows.append({
                    "name": name, "ecosystem": e["ecosystem"], "version": e["version_constraint"],
                    "category": e["category"], "dev_only": e["dev_only"], "role": e["role"],
                    "bucket": bucket,
                    "in_dependency_snapshot": True,
                    "in_readme_dependencies_section": name in in_section,
                    "in_readme_prose_elsewhere": in_prose,
                    "in_claims_json": in_claims,
                    "corroboration_score": score,
                    "status": "VERIFIED" if score >= 2 else "NEEDS_REVIEW",
                })
    scoped_claims = []
    for match in _UNQUALIFIED_DEPENDENCY_CLAIM_RE.finditer(readme_text):
        start = max(0, match.start() - 120)
        end = min(len(readme_text), match.end() + 120)
        clause = readme_text[start:end]
        qualifier = _DEPENDENCY_SCOPE_QUALIFIER_RE.search(clause)
        if qualifier:
            scoped_claims.append({
                "text": match.group(0), "category_claimed": qualifier.group(0).strip(),
                "context": clause.replace("\n", " ").strip(),
            })
    return {"rows": rows, "scoped_claims": scoped_claims}


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
