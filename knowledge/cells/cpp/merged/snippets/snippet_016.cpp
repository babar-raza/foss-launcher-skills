TEST(CompatibilityTests, file_and_stream_roundtrip_preserve_data_validations)
{
    TempDir temp("compat-validations");
    const auto filePath = temp.Path("validations.xlsx");
    auto workbook = CreateValidationWorkbook();
    workbook.Save(filePath.string());

    std::vector<std::uint8_t> stream;
    workbook.Save(stream, SaveFormat::Xlsx);

    Workbook fromFile(filePath.string());
    Workbook fromStream(stream);
    AssertValidations(fromFile);
    AssertValidations(fromStream);
}