TEST(CompatibilityTests, file_and_stream_roundtrip_preserve_autofilter)
{
    TempDir temp("compat-autofilter");
    const auto filePath = temp.Path("autofilter.xlsx");
    auto workbook = CreateAutoFilterWorkbook();
    workbook.Save(filePath.string());

    std::vector<std::uint8_t> stream;
    workbook.Save(stream, SaveFormat::Xlsx);

    Workbook fromFile(filePath.string());
    Workbook fromStream(stream);
    AssertAutoFilter(fromFile);
    AssertAutoFilter(fromStream);
}