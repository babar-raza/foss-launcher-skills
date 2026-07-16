from scripts.pipeline.content_eval.evaluators.format_completeness import _alias_variants


def test_alias_variants_follow_chains_without_matching_by_direction() -> None:
    assert _alias_variants("msg") == {"msg", "outlookmessage", "outlookmsg"}
    assert "cfb" not in _alias_variants("msg")


def test_alias_variants_treat_reverse_aliases_as_equivalent() -> None:
    assert _alias_variants("xlsx") == {"xlsx", "excelopenxml"}
