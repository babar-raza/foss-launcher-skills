def test_registry_raises_for_unknown_names() -> None:
    """Unknown normalized names should raise SymbologyNotFoundError."""
    registry = SymbologyRegistry()

    with pytest.raises(SymbologyNotFoundError, match="missing"):
        registry.get_definition(" missing ")