def test_registry_rejects_duplicate_aliases() -> None:
    """Alias collisions should fail before mutating the registry."""
    registry = SymbologyRegistry()
    registry.register(_build_definition("code128", aliases=("code-128",)))

    with pytest.raises(ValueError, match="code-128"):
        registry.register(_build_definition("ean13", aliases=(" code-128 ",)))