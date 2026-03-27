"""Configuration for content_eval evaluators and thresholds."""

from __future__ import annotations

# All available evaluators in execution order
ALL_EVALUATORS = [
    "api_accuracy",
    "api_backtick",
    "claim_coverage",
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
]

# Default evaluators (fast, deterministic, production-ready)
DEFAULT_EVALUATORS = [
    "api_accuracy",
    "platform_purity",
    "forbidden_claims",
    "page_role",
    "structure",
    "risk_language",
    "evidence_depth",
    "prose_truth",
    "code_plausibility",
]

# Platform foreign-code patterns: (regex, description)
# Applied to code blocks to detect wrong-language contamination
PLATFORM_FOREIGN_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "dotnet": [
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
}

# Language tag normalization: content lang tags → knowledge platform names
LANG_TO_PLATFORM = {
    "python": "python",
    "py": "python",
    "csharp": "dotnet",
    "cs": "dotnet",
    "c#": "dotnet",
    "java": "java",
    "cpp": "cpp",
    "c++": "cpp",
    "typescript": "typescript",
    "ts": "typescript",
    "javascript": "javascript",
    "js": "javascript",
}

# Platform → expected code block language tags
PLATFORM_EXPECTED_LANGS = {
    "dotnet": {"csharp", "cs", "c#"},
    "python": {"python", "py"},
    "java": {"java"},
    "cpp": {"cpp", "c++"},
    "typescript": {"typescript", "ts"},
    "javascript": {"javascript", "js"},
}

# Prose contamination patterns (checked in prose, not code)
PROSE_FOREIGN_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "dotnet": [
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
    (r"\benterprise[\s-]?grade\b", "Marketing language: 'enterprise-grade'", "INFO"),
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
