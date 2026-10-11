TEST(OpenXmlFeatureGoldenTests, defined_names_roundtrip_and_emit_expected_markup)
{
    TempDir temp("golden-defined-names");
    const auto path = temp.Path("defined-names.xlsx");
    auto workbook = CreateDefinedNamesWorkbook();
    workbook.Save(path.string());

    const auto workbookXml = Package::ReadEntryText(path, "xl/workbook.xml");
    EXPECT_TRUE(Contains(workbookXml, "<definedNames>"));
    EXPECT_TRUE(Contains(workbookXml, "name=\"GlobalRange\""));
    EXPECT_TRUE(Contains(workbookXml, "hidden=\"1\""));
    EXPECT_TRUE(Contains(workbookXml, "comment=\"Primary range\""));
    EXPECT_TRUE(Contains(workbookXml, "name=\"LocalCell\""));
    EXPECT_TRUE(Contains(workbookXml, "localSheetId=\"1\""));
    EXPECT_TRUE(Contains(workbookXml, "name=\"_xlnm.Print_Area\""));
    EXPECT_TRUE(Contains(workbookXml, "name=\"_xlnm.Print_Titles\""));

    Workbook loaded(path.string());
    AssertDefinedNames(loaded);
}