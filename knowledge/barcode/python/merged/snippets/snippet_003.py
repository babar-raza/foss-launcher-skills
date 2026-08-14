def test_barcode_service_rejects_blank_and_non_string_symbologies(
    symbology: object,
) -> None:
    """Invalid public symbology selectors should fail before registry lookup."""
    service = BarcodeService(
        registry=SymbologyRegistry(),
        options_resolver=OptionsResolver(),
    )

    with pytest.raises(InvalidInputError, match="symbology"):
        service.generate(symbology, "ABC123")