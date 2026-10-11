def test_registry_derives_text_policy_from_the_profile() -> None:
    """The registry should expose the profile-owned text policy directly."""
    registry = SymbologyRegistry()
    text_policy = TestTextPolicy()
    definition = _build_definition("code128", text_policy=text_policy)

    registry.register(definition)

    assert "text_policy" not in {field.name for field in fields(SymbologyDefinition)}
    assert registry.get_text_policy("code128") is registry.get_profile("code128").text_policy
    assert registry.get_text_policy("code128") is text_policy