TEST(CompatibilityTests, file_and_stream_roundtrip_preserve_defined_names)
{
    TempDir temp("compat-defined-names");
    const auto filePath = temp.Path("defined-names.xlsx");
    auto workbook = CreateDefinedNamesWorkbook();
    workbook.Save(filePath.string());

    std::vector<std::uint8_t> stream;
    workbook.Save(stream, SaveFormat::Xlsx);

    Workbook fromFile(filePath.string());
    Workbook fromStream(stream);
    AssertDefinedNames(fromFile);
    AssertDefinedNames(fromStream);
}