TEST(OpenXmlFeatureGoldenTests, autofilter_omits_invalid_dxf_references)
{
    TempDir temp("golden-autofilter-invalid-dxf");
    const auto path = temp.Path("autofilter-invalid-dxf.xlsx");
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];
    sheet.SetName("InvalidDxf");
    sheet.GetCells()["A1"].PutValue("Status");
    sheet.GetCells()["A2"].PutValue("Open");
    sheet.GetCells()["A3"].PutValue("Closed");
    sheet.GetCells()["B1"].PutValue("Amount");
    sheet.GetCells()["B2"].PutValue(10);
    sheet.GetCells()["B3"].PutValue(20);
    sheet.GetAutoFilter().SetRange("A1:B3");

    auto column = sheet.GetAutoFilter().GetFilterColumns()[sheet.GetAutoFilter().GetFilterColumns().Add(0)];
    column.GetColorFilter().SetEnabled(true);
    column.GetColorFilter().SetDifferentialStyleId(9);
    column.GetColorFilter().SetCellColor(true);

    sheet.GetAutoFilter().GetSortState().SetRef("A2:B3");
    auto sortCondition = sheet.GetAutoFilter().GetSortState().GetSortConditions()[sheet.GetAutoFilter().GetSortState().GetSortConditions().Add("B2:B3")];
    sortCondition.SetSortBy("value");
    sortCondition.SetDifferentialStyleId(8);
    workbook.Save(path.string());

    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");
    EXPECT_TRUE(Contains(worksheetXml, "<autoFilter ref=\"A1:B3\""));
    EXPECT_FALSE(Contains(worksheetXml, "<colorFilter"));
    EXPECT_FALSE(Contains(worksheetXml, "dxfId=\"8\""));
    EXPECT_FALSE(Contains(worksheetXml, "dxfId=\"9\""));

    Workbook loaded(path.string());
    EXPECT_EQ("A1:B3", loaded.GetWorksheets()[0].GetAutoFilter().GetRange());
    EXPECT_EQ(0, loaded.GetWorksheets()[0].GetAutoFilter().GetFilterColumns().GetCount());
    ASSERT_EQ(1, loaded.GetWorksheets()[0].GetAutoFilter().GetSortState().GetSortConditions().GetCount());
    EXPECT_FALSE(loaded.GetWorksheets()[0].GetAutoFilter().GetSortState().GetSortConditions()[0].GetDifferentialStyleId().has_value());
}