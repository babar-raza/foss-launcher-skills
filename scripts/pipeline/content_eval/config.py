"""Configuration for content_eval evaluators and thresholds."""

from __future__ import annotations

# All available evaluators in execution order
ALL_EVALUATORS = [
    "api_accuracy",
    "api_backtick",
    "claim_coverage",
    "code_block_api",
    "content_substance",
    "dead_internal_link",
    "description_completeness",
    "platform_purity",
    "forbidden_claims",
    "page_role",
    "structure",
    "prose_truth",
    "format_truth",
    "install_recipe",
    "limitations_check",
    "risk_language",
    "evidence_depth",
    "code_plausibility",
    "coverage",
    "type_accuracy",
    "prose_claim_binding",
    "api_completeness",
    "code_syntax_check",
    "namespace_correctness",
    "format_completeness",
    "member_validity",
    "prose_grounding",
    "version_claim_check",
    "capability_claim_check",
    "encoding_check",
    "consumer_usefulness",
    "private_api_usage",
    "evidence_format_validity",
    "cta_wording",
    "code_prose_alignment",  # TC-EVAL-003: EXPERIMENTAL
    "generic_description_check",  # TC-GDF-001: detect generic fallback descriptions in _index.md
    "duplicate_content",  # RC-W1-005 (MT026 blind-spot audit): whole-page duplicate/alias-collision detection
    "module_compilability",  # RC-tex-python-05 (MT037 blind-spot audit): verify cited API modules actually compile
    "example_execution",  # MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION C8: inherit-first execution-proof + tier-1 syntax check
]

# FREEZE-03: Canonical evaluators — contribute to the frontmatter grade letter.
# These are the 10 evaluators across the 4 canonical dimensions defined in
# GRADE_CONTRACT.md §1-3: Safety, Factual Accuracy, Usability, Completeness.
CANONICAL_EVALUATORS = frozenset({
    # Safety (FAIL → F)
    "forbidden_claims",
    "platform_purity",
    "type_accuracy",
    # Factual Accuracy (FAIL → ceiling D)
    "api_accuracy",
    "prose_truth",
    "format_truth",
    # Usability (FAIL → ceiling C)
    "code_plausibility",
    "code_syntax_check",
    "consumer_usefulness",
    # Completeness (FAIL → ceiling C)
    "api_completeness",
    "description_completeness",
    # Grounding (EG_GROUNDING WARN → ceiling B; graduated TC-SFH-003 2026-07-14)
    "evidence_depth",
})

# FREEZE-03: Experimental evaluators — run during evaluation and appear in
# the manifest and reports, but do NOT affect the canonical frontmatter grade.
# New evaluators MUST start here.  Graduation to CANONICAL_EVALUATORS requires
# ≥14 days stable + corpus-wide validation + maintainer sign-off.
# See GRADE_CONTRACT.md §6 for graduation policy.
EXPERIMENTAL_EVALUATORS = frozenset({
    "api_backtick",
    "claim_coverage",
    "code_block_api",
    "content_substance",
    "coverage",
    "dead_internal_link",
    "encoding_check",
    "format_completeness",
    "install_recipe",
    "limitations_check",
    "member_validity",
    "namespace_correctness",
    "page_role",
    "prose_claim_binding",
    "prose_grounding",
    "risk_language",
    "structure",
    "version_claim_check",
    "capability_claim_check",
    "private_api_usage",
    "evidence_format_validity",
    # code_prose_alignment: graduated to DEFAULT (TC-PROMOTE-001, 2026-06-13)
    "generic_description_check",  # TC-GDF-001: EXPERIMENTAL — index placeholder detection
    "duplicate_content",  # RC-W1-005: EXPERIMENTAL — new evaluators MUST start here per GRADE_CONTRACT.md §6
    "module_compilability",  # RC-tex-python-05: EXPERIMENTAL — new evaluators MUST start here per GRADE_CONTRACT.md §6
    "example_execution",  # MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION C8: EXPERIMENTAL — new evaluators MUST start here per GRADE_CONTRACT.md §6
})

# Default evaluators (fast, deterministic, production-ready)
DEFAULT_EVALUATORS = [
    "api_accuracy",
    "content_substance",
    "description_completeness",
    "platform_purity",
    "forbidden_claims",
    "page_role",
    "structure",
    "risk_language",
    "evidence_depth",
    "prose_truth",
    "code_plausibility",
    "format_truth",
    "format_completeness",
    "type_accuracy",
    "coverage",
    "install_recipe",
    "limitations_check",
    "prose_claim_binding",
    "api_completeness",
    "code_syntax_check",
    "namespace_correctness",
    "member_validity",
    "prose_grounding",
    "code_block_api",
    "dead_internal_link",
    "version_claim_check",
    "capability_claim_check",
    "encoding_check",
    "consumer_usefulness",
    "cta_wording",  # graduated from EXPERIMENTAL 2026-06-09 (TC-CTA-GRADUATION)
    "code_prose_alignment",  # graduated from EXPERIMENTAL 2026-06-13 (TC-PROMOTE-001), WARN-only
    "evidence_format_validity",  # added to DEFAULT 2026-07-12 — surfaces stale evidence.formats entries in reports
    "generic_description_check",  # TC-GDF-001: EXPERIMENTAL — detect placeholder descriptions in _index.md
    "duplicate_content",  # RC-W1-005: detect duplicate/near-duplicate pages + alias-slug collisions (blog/kb)
    "example_execution",  # MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION C8: inherit-first execution-proof + tier-1 syntax check, no grade effect
]

# Platform foreign-code patterns: (regex, description)
# Applied to code blocks to detect wrong-language contamination
PLATFORM_FOREIGN_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "net": [
        (r"\bdef\s+\w+\s*\(", "Python function definition"),
        (r"\bself\.\w+", "Python self reference"),
        (r"\bSystem\.out\.println", "Java print statement"),
        (r"\bArrayList\b(?!.*//)", "Java ArrayList"),
        (r"\bimport\s+\w+\.\w+(?!;)", "Python-style import (missing semicolon)"),
        (r"#\s*include\s*<", "C++ include directive"),
        (r"\bconsole\.log\(", "JavaScript console.log"),
    ],
    "python": [
        (r"\busing\s+\w+\.\w+;", ".NET using statement"),
        (r"\bnew\s+\w+\s*\(", "Java/C# constructor syntax"),
        (r"\bConsole\.WriteLine", ".NET console output"),
        (r"\bSystem\.out\.println", "Java print statement"),
        (r"\bpublic\s+(?:class|static|void)\b", "Java/C# access modifier"),
        (r"\bvar\s+\w+\s*=", "C# var declaration"),
        (r"#\s*include\s*<", "C++ include directive"),
    ],
    "java": [
        (r"\bdef\s+\w+\s*\(", "Python function definition"),
        (r"\bself\.\w+", "Python self reference"),
        (r"\busing\s+\w+\.\w+;", "C# using statement"),
        (r"\bConsole\.WriteLine", ".NET console output"),
        (r"\bconsole\.log\(", "JavaScript console.log"),
        (r"#\s*include\s*<", "C++ include directive"),
        (r"\bfrom\s+\w+\s+import\b", "Python from-import"),
    ],
    "cpp": [
        (r"\bdef\s+\w+\s*\(", "Python function definition"),
        (r"\bself\.\w+", "Python self reference"),
        (r"\bSystem\.out\.println", "Java print statement"),
        (r"\bConsole\.WriteLine", ".NET console output"),
        (r"\bconsole\.log\(", "JavaScript console.log"),
        (r"\bpip\s+install\b", "Python pip install"),
        (r"\bfrom\s+\w+\s+import\b", "Python from-import"),
    ],
    "typescript": [
        (r"\bdef\s+\w+\s*\(", "Python function definition"),
        (r"\bself\.\w+", "Python self reference"),
        (r"\bSystem\.out\.println", "Java print statement"),
        (r"\bConsole\.WriteLine", ".NET console output"),
        (r"#\s*include\s*<", "C++ include directive"),
    ],
    "javascript": [
        (r"\bdef\s+\w+\s*\(", "Python function definition"),
        (r"\bself\.\w+", "Python self reference"),
        (r"\bSystem\.out\.println", "Java print statement"),
        (r"\bConsole\.WriteLine", ".NET console output"),
        (r"#\s*include\s*<", "C++ include directive"),
    ],
    "rust": [
        # NOTE: no `self.`-based pattern here — `self.field` (and even
        # `self.field = value`) is idiomatic Rust, unlike every other
        # non-Python platform where it signals Python contamination.
        (r"\bdef\s+\w+\s*\(", "Python function definition"),
        (r"\bSystem\.out\.println", "Java print statement"),
        (r"\bConsole\.WriteLine", ".NET console output"),
        (r"\bconsole\.log\(", "JavaScript console.log"),
        (r"#\s*include\s*<", "C++ include directive"),
        (r"\bfrom\s+\w+\s+import\b", "Python from-import"),
    ],
}

# Language tag normalization: content lang tags → knowledge platform names
LANG_TO_PLATFORM = {
    "python": "python",
    "py": "python",
    "csharp": "net",
    "cs": "net",
    "c#": "net",
    "java": "java",
    "cpp": "cpp",
    "c++": "cpp",
    "typescript": "typescript",
    "ts": "typescript",
    "javascript": "javascript",
    "js": "javascript",
    "rust": "rust",
    "rs": "rust",
}

# Platform → expected code block language tags
PLATFORM_EXPECTED_LANGS = {
    "net": {"csharp", "cs", "c#"},
    "python": {"python", "py"},
    "java": {"java"},
    "cpp": {"cpp", "c++"},
    "typescript": {"typescript", "ts"},
    "javascript": {"javascript", "js"},
    "rust": {"rust", "rs"},
}

# Prose contamination patterns (checked in prose, not code)
PROSE_FOREIGN_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "net": [
        (r"\bpip\s+install\b", "Python pip install in .NET page"),
        (r"\bnpm\s+install\b", "npm install in .NET page"),
        (r"\bmaven\b", "Maven reference in .NET page"),
    ],
    "python": [
        (r"\bNuGet\b", "NuGet reference in Python page"),
        (r"\bdotnet\s+add\s+package\b", "dotnet CLI in Python page"),
        (r"\bmaven\b", "Maven reference in Python page"),
    ],
    "java": [
        (r"\bpip\s+install\b", "Python pip install in Java page"),
        (r"\bNuGet\b", "NuGet reference in Java page"),
        (r"\bnpm\s+install\b", "npm install in Java page"),
    ],
    "cpp": [
        (r"\bpip\s+install\b", "Python pip install in C++ page"),
        (r"\bNuGet\b", "NuGet reference in C++ page"),
        (r"\bmaven\b", "Maven reference in C++ page"),
    ],
    "rust": [
        (r"\bpip\s+install\b", "Python pip install in Rust page"),
        (r"\bNuGet\b", "NuGet reference in Rust page"),
        (r"\bmaven\b", "Maven reference in Rust page"),
        (r"\bnpm\s+install\b", "npm install in Rust page"),
    ],
    # G-TS-03 (MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH TC-MT040-19): typescript
    # and javascript previously had no entry at all, so platform_purity.py
    # never checked TS/JS page prose for cross-platform install-command
    # contamination (every OTHER platform above already does). `npm install`
    # is native to these two platforms and is deliberately excluded, mirroring
    # how each platform's own list above never flags its own native command.
    "typescript": [
        (r"\bpip\s+install\b", "Python pip install in TypeScript page"),
        (r"\bNuGet\b", "NuGet reference in TypeScript page"),
        (r"\bdotnet\s+add\s+package\b", "dotnet CLI in TypeScript page"),
        (r"\bmaven\b", "Maven reference in TypeScript page"),
        (r"\bcargo\s+add\b", "cargo add in TypeScript page"),
        (r"\bgo\s+get\b", "go get in TypeScript page"),
    ],
    "javascript": [
        (r"\bpip\s+install\b", "Python pip install in JavaScript page"),
        (r"\bNuGet\b", "NuGet reference in JavaScript page"),
        (r"\bdotnet\s+add\s+package\b", "dotnet CLI in JavaScript page"),
        (r"\bmaven\b", "Maven reference in JavaScript page"),
        (r"\bcargo\s+add\b", "cargo add in JavaScript page"),
        (r"\bgo\s+get\b", "go get in JavaScript page"),
    ],
}

# Risk language patterns
RISK_LANGUAGE_PATTERNS: list[tuple[str, str, str]] = [
    # (regex, description, severity)
    (r"\bseamless(?:ly)?\b", "Unsupported superlative: 'seamless'", "WARN"),
    (r"\brobust\b", "Unsupported superlative: 'robust'", "INFO"),
    (r"\bbest\s+(?:in\s+class|available|possible)\b", "Unsupported superlative: 'best'", "WARN"),
    (r"\bfastest\b", "Unsupported performance claim: 'fastest'", "WARN"),
    (r"\blightweight\b", "Unsupported claim: 'lightweight'", "INFO"),
    (r"\bhigh[\s-]?performance\b", "Unsupported performance claim", "WARN"),
    (r"\bfully\s+support(?:s|ed)?\b", "Overstated completeness: 'fully supports'", "WARN"),
    (r"\bcomplete(?:ly)?\s+(?:support|compatible|implement)", "Overstated completeness", "WARN"),
    (r"\ball\s+(?:features|formats|platforms)\b", "Overbroad claim: 'all'", "WARN"),
    (r"\b100\s*%\s*(?:compatible|accurate|supported)\b", "Unsupported 100% claim", "FAIL"),
    (r"\benterprise[\s\-\u2011]?grade\b", "Positioning language: 'enterprise-grade' (advisory)", "INFO"),
    (r"\benterprise[\s\-\u2011]?(?:ready|level|class)\b", "Positioning language: 'enterprise-ready/level/class' (advisory)", "INFO"),
    (r"\bcommercial[\s\-]?grade\b", "Positioning language: 'commercial-grade' (advisory)", "INFO"),
    (r"\bproduction[\s-]?ready\b", "Unsupported claim: 'production-ready'", "INFO"),
    (r"\bindustry[\s-]?leading\b", "Marketing language: 'industry-leading'", "WARN"),
    (r"\bzero[\s-]?(?:config|dependency|overhead)\b", "Unsupported 'zero' claim", "WARN"),
    (r"\bno\s+limitations?\b", "Dangerous claim: 'no limitations'", "FAIL"),
    (r"\bunlimited\b", "Unsupported claim: 'unlimited'", "WARN"),
    (r"\bguarantee[ds]?\b", "Unsupported guarantee", "WARN"),
    (r"\bperfect(?:ly)?\b", "Unsupported claim: 'perfect'", "WARN"),
    (r"\bflawless\b", "Unsupported claim: 'flawless'", "WARN"),
    (r"\bout[\s-]?of[\s-]?the[\s-]?box\b", "Unsupported claim: 'out of the box'", "INFO"),
]

# Placeholder patterns that should not appear in published content
PLACEHOLDER_PATTERNS = [
    (r"\{TODO\}", "TODO placeholder"),
    (r"\bTBD\b", "TBD placeholder"),
    (r"\bPLACEHOLDER\b", "PLACEHOLDER text"),
    (r"\bLorem\s+ipsum\b", "Lorem ipsum placeholder"),
    (r"\bXXX\b", "XXX marker"),
    (r"\bFIXME\b", "FIXME marker"),
    (r"\bHACK\b", "HACK marker"),
]
