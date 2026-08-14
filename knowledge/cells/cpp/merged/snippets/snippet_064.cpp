TEST(WorksheetFeatureUnitTests, autofilter_apis_mutate_expected_settings)
{
    auto workbook = CreateAutoFilterWorkbook();
    AssertAutoFilter(workbook);

    auto& sheet = workbook.GetWorksheets()[0];
    EXPECT_THROW(sheet.GetAutoFilter().GetFilterColumns().Add(-1), CellsException);
    EXPECT_THROW(sheet.GetAutoFilter().GetFilterColumns().Add(0), CellsException);
    EXPECT_THROW(sheet.GetAutoFilter().GetSortState().GetSortConditions().Add("1A"), CellsException);

    sheet.GetAutoFilter().GetFilterColumns().RemoveAt(4);
    EXPECT_EQ(4, sheet.GetAutoFilter().GetFilterColumns().GetCount());
    sheet.GetAutoFilter().Clear();
    EXPECT_EQ("", sheet.GetAutoFilter().GetRange());
    EXPECT_EQ(0, sheet.GetAutoFilter().GetFilterColumns().GetCount());
    EXPECT_EQ(0, sheet.GetAutoFilter().GetSortState().GetSortConditions().GetCount());
}