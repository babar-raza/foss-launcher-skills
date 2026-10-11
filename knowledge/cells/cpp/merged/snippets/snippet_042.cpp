TEST(WorkbookMetadataGoldenTests, workbook_metadata_roundtrip_and_emit_expected_markup)
{
    TempDir temp("golden-workbook-metadata");
    const auto path = temp.Path("workbook-metadata.xlsx");
    auto workbook = CreateWorkbookMetadataWorkbook();
    workbook.Save(path.string());

    const auto workbookXml = Package::ReadEntryText(path, "xl/workbook.xml");
    const auto coreXml = Package::ReadEntryText(path, "docProps/core.xml");
    const auto appXml = Package::ReadEntryText(path, "docProps/app.xml");

    EXPECT_TRUE(Contains(workbookXml, "<workbookPr"));
    EXPECT_TRUE(Contains(workbookXml, "codeName=\"WorkbookCode\""));
    EXPECT_TRUE(Contains(workbookXml, "showObjects=\"placeholders\""));
    EXPECT_TRUE(Contains(workbookXml, "<workbookProtection"));
    EXPECT_TRUE(Contains(workbookXml, "workbookPassword=\"ABCD\""));
    EXPECT_TRUE(Contains(workbookXml, "<bookViews>"));
    EXPECT_TRUE(Contains(workbookXml, "activeTab=\"1\""));
    EXPECT_TRUE(Contains(workbookXml, "showSheetTabs=\"0\""));
    EXPECT_TRUE(Contains(workbookXml, "<calcPr"));
    EXPECT_TRUE(Contains(workbookXml, "calcMode=\"manual\""));
    EXPECT_TRUE(Contains(workbookXml, "refMode=\"R1C1\""));
    EXPECT_TRUE(Contains(coreXml, "Quarterly Summary"));
    EXPECT_TRUE(Contains(coreXml, "Automation"));
    EXPECT_TRUE(Contains(appXml, "Aspose.Cells_FOSS Tests"));
    EXPECT_TRUE(Contains(appXml, "https://example.com/base/"));

    Workbook loaded(path.string());
    AssertWorkbookMetadata(loaded);
}