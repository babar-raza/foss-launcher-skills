TEST(WorkbookPortingTests, WorksheetsVisibilityAndActiveSheetRoundTrip)
{
    TempDir temp;
    const auto path = temp.Path("sheets.xlsx");

    Workbook workbook;
    workbook.GetWorksheets()[0].SetName("Visible");
    const int hiddenIndex = workbook.GetWorksheets().Add("Hidden");
    workbook.GetWorksheets()[hiddenIndex].SetVisibilityType(VisibilityType::Hidden);
    const int veryHiddenIndex = workbook.GetWorksheets().Add("VeryHidden");
    workbook.GetWorksheets()[veryHiddenIndex].SetVisibilityType(VisibilityType::VeryHidden);
    workbook.GetWorksheets().SetActiveSheetIndex(hiddenIndex);
    workbook.Save(path.string());

    Workbook loaded(path.string());
    ASSERT_EQ(3, loaded.GetWorksheets().GetCount());
    EXPECT_EQ("Visible", loaded.GetWorksheets()[0].GetName());
    EXPECT_EQ("Hidden", loaded.GetWorksheets()[1].GetName());
    EXPECT_EQ("VeryHidden", loaded.GetWorksheets()[2].GetName());
    EXPECT_EQ(VisibilityType::Hidden, loaded.GetWorksheets()[1].GetVisibilityType());
    EXPECT_EQ(VisibilityType::VeryHidden, loaded.GetWorksheets()[2].GetVisibilityType());
    EXPECT_EQ(hiddenIndex, loaded.GetWorksheets().GetActiveSheetIndex());
}