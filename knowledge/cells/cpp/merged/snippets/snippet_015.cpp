TEST(CompatibilityTests, file_and_stream_roundtrip_preserve_worksheet_settings)
{
    TempDir temp("compat-worksheet-settings");
    const auto filePath = temp.Path("worksheet-settings.xlsx");
    auto workbook = CreateWorksheetSettingsWorkbook();
    workbook.Save(filePath.string());

    std::vector<std::uint8_t> stream;
    workbook.Save(stream, SaveFormat::Xlsx);

    Workbook fromFile(filePath.string());
    Workbook fromStream(stream);
    AssertWorksheetSettings(fromFile);
    AssertWorksheetSettingsScenarioHasVisibleSheet(fromFile);
    AssertWorksheetSettings(fromStream);
    AssertWorksheetSettingsScenarioHasVisibleSheet(fromStream);
}