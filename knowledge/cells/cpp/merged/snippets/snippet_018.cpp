TEST(CompatibilityTests, file_and_stream_roundtrip_preserve_advanced_conditional_formattings)
{
    TempDir temp("compat-advanced-conditional-formatting");
    const auto filePath = temp.Path("advanced-conditional-formatting.xlsx");
    auto workbook = CreateAdvancedConditionalFormattingWorkbook();
    workbook.Save(filePath.string());

    std::vector<std::uint8_t> stream;
    workbook.Save(stream, SaveFormat::Xlsx);

    Workbook fromFile(filePath.string());
    Workbook fromStream(stream);
    AssertAdvancedConditionalFormattings(fromFile);
    AssertAdvancedConditionalFormattings(fromStream);
}