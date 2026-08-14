def test_default_service_bootstrap_wires_registry_and_options_resolver() -> None:
    """The default service bootstrap should wire a fresh registry and resolver."""
    service = build_default_service()

    assert isinstance(service, BarcodeService)
    assert isinstance(service.registry, SymbologyRegistry)
    assert isinstance(service.options_resolver, OptionsResolver)
    assert service.registry.get_definition("upce").name == "upce"