def test_registry_rejects_duplicate_canonical_names() -> None:
    """Canonical-name collisions should fail before mutating the registry."""
    registry = SymbologyRegistry()
    registry.register(_build_definition("code128"))

    with pytest.raises(ValueError, match="code128"):
        registry.register(_build_definition(" CODE128 "))