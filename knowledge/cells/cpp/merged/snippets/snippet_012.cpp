TEST(CompatibilityTests, excel_input_autofilter_roundtrip_preserves_header_only_range)
{
    const auto inputPath = ResolveRepositoryFile("Input", "Autofilter.xlsx");
    Workbook workbook(inputPath.string());
    EXPECT_EQ("A2:C2", workbook.GetWorksheets()[0].GetAutoFilter().GetRange());
    EXPECT_EQ(0, workbook.GetWorksheets()[0].GetAutoFilter().GetFilterColumns().GetCount());
    EXPECT_EQ(0, workbook.GetWorksheets()[0].GetAutoFilter().GetSortState().GetSortConditions().GetCount());

    TempDir temp("compat-input-autofilter");
    const auto roundtripPath = temp.Path("autofilter-roundtrip.xlsx");
    workbook.Save(roundtripPath.string());

    Workbook reloaded(roundtripPath.string());
    EXPECT_EQ("A2:C2", reloaded.GetWorksheets()[0].GetAutoFilter().GetRange());
    EXPECT_EQ(0, reloaded.GetWorksheets()[0].GetAutoFilter().GetFilterColumns().GetCount());
    EXPECT_EQ(0, reloaded.GetWorksheets()[0].GetAutoFilter().GetSortState().GetSortConditions().GetCount());

    const auto workbookXml = Package::ReadEntryText(roundtripPath, "xl/workbook.xml");
    const auto worksheetXml = Package::ReadEntryText(roundtripPath, "xl/worksheets/sheet1.xml");
    EXPECT_TRUE(Contains(worksheetXml, "<autoFilter ref=\"A2:C2\""));
    EXPECT_TRUE(Contains(workbookXml, "name=\"_xlnm._FilterDatabase\""));
    EXPECT_TRUE(Contains(workbookXml, "$A$2:$C$2"));
}