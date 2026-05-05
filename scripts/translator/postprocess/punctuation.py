"""Post-translation punctuation normalization for CJK languages."""
from __future__ import annotations
import re

_DOUBLE_PERIOD_CJK = re.compile(r'\u3002\.')          # 。.
_DOUBLE_ASCII_PERIOD = re.compile(r'(?<!\.)\.\.(?!\.)') # .. but not ...
_DOUBLE_CJK_PERIOD = re.compile(r'\u3002\u3002')       # 。。
_TRAILING_COLON_COLON = re.compile(r'::(?=\s|$)')      # :: at end of phrase
_DOUBLE_CJK_COMMA = re.compile(r'\u3001\u3001')        # 、、

_CJK_LOCALES = frozenset({"ja", "ko", "zh"})


def normalize_punctuation(text: str, tgt_lang: str) -> str:
    """Apply language-specific punctuation cleanup after translation."""
    if tgt_lang not in _CJK_LOCALES:
        return text

    if tgt_lang == "ja":
        text = _DOUBLE_PERIOD_CJK.sub('\u3002', text)   # 。. → 。
        text = _DOUBLE_CJK_PERIOD.sub('\u3002', text)   # 。。 → 。
        text = _DOUBLE_CJK_COMMA.sub('\u3001', text)    # 、、 → 、

    # All CJK
    text = _DOUBLE_ASCII_PERIOD.sub('.', text)
    text = _TRAILING_COLON_COLON.sub(':', text)

    return text
