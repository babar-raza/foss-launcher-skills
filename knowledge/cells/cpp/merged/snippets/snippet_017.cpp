TEST(CompatibilityTests, file_and_stream_roundtrip_preserve_conditional_formattings)
{
    TempDir temp("compat-conditional-formatting");
    const auto filePath = temp.Path("conditional-formatting.xlsx");
    auto workbook = CreateConditionalFormattingWorkbook();
    workbook.Save(filePath.string());

    std::vector<std::uint8_t> stream;
    workbook.Save(stream, SaveFormat::Xlsx);

    Workbook fromFile(filePath.string());
    Workbook fromStream(stream);
    AssertConditionalFormattings(fromFile);
    AssertConditionalFormattings(fromStream);
}