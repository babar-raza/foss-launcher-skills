TEST(CompatibilityTests, file_and_stream_roundtrip_preserve_page_setup)
{
    TempDir temp("compat-page-setup");
    const auto filePath = temp.Path("page-setup.xlsx");
    auto workbook = CreatePageSetupWorkbook();
    workbook.Save(filePath.string());

    std::vector<std::uint8_t> stream;
    workbook.Save(stream, SaveFormat::Xlsx);

    Workbook fromFile(filePath.string());
    Workbook fromStream(stream);
    AssertPageSetup(fromFile);
    AssertPageSetup(fromStream);
}