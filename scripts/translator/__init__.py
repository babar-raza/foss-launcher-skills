"""
aspose.org Translation Subsystem
Self-contained translation package for Hugo multi-site markdown content.
"""
__version__ = "1.0.0"

ALL_LOCALES = [
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi",
    "fr", "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt",
    "lv", "ms", "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr",
    "sv", "th", "tr", "uk", "vi", "zh",
]

LOCALE_NAMES = {
    "ar": "Arabic", "bg": "Bulgarian", "ca": "Catalan", "cs": "Czech",
    "da": "Danish", "de": "German", "el": "Greek", "es": "Spanish",
    "fa": "Persian", "fi": "Finnish", "fr": "French", "he": "Hebrew",
    "hi": "Hindi", "hr": "Croatian", "hu": "Hungarian", "id": "Indonesian",
    "it": "Italian", "ja": "Japanese", "ko": "Korean", "lt": "Lithuanian",
    "lv": "Latvian", "ms": "Malay", "nl": "Dutch", "no": "Norwegian",
    "pl": "Polish", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian",
    "sk": "Slovak", "sr": "Serbian", "sv": "Swedish", "th": "Thai",
    "tr": "Turkish", "uk": "Ukrainian", "vi": "Vietnamese", "zh": "Chinese",
}


class TranslatorError(Exception):
    """Base exception for translator subsystem."""


class FrontmatterParseError(TranslatorError):
    """Raised when YAML frontmatter cannot be parsed."""


class PlaceholderLeakError(TranslatorError):
    """Raised when placeholder tokens survive translation."""


class ConfigurationError(TranslatorError):
    """Raised when required configuration is missing."""


class BackendUnavailableError(TranslatorError):
    """Raised when a translation backend cannot be reached."""
# foss: provenance_shim is a standalone module
