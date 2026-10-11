TEST(CompatibilityTests, file_and_stream_roundtrip_preserve_workbook_metadata)
{
    TempDir temp("compat-workbook-metadata");
    const auto filePath = temp.Path("workbook-metadata.xlsx");
    auto workbook = CreateWorkbookMetadataWorkbook();
    workbook.Save(filePath.string());

    std::vector<std::uint8_t> stream;
    workbook.Save(stream, SaveFormat::Xlsx);

    Workbook fromFile(filePath.string());
    Workbook fromStream(stream);
    AssertWorkbookMetadata(fromFile);
    AssertWorkbookMetadata(fromStream);
}