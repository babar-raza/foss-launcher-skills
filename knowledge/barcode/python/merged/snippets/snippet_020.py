def test_default_registry_bootstrap_registers_canonical_names_and_aliases(
    name: str,
    expected_alias: str,
    expected_quiet_zone: float,
) -> None:
    """The default bootstrap should publish all canonical ids and aliases."""
    registry = build_default_registry()

    canonical = registry.get_definition(name)
    alias = registry.get_definition(expected_alias)

    assert alias is canonical
    assert canonical.name == name
    assert canonical.aliases == (expected_alias,)
    assert canonical.profile.name == name
    assert canonical.profile.capabilities == _expected_capabilities()

    if name == "code128":
        _assert_code128_profile(canonical.profile)
    else:
        _assert_ean_upc_profile(canonical.profile, quiet_zone=expected_quiet_zone)