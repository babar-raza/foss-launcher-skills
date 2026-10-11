TEST(WorksheetFeatureUnitTests, worksheet_view_apis_mutate_expected_settings)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];

    sheet.SetTabColor(Color::FromArgb(255, 34, 68, 102));
    sheet.SetShowGridlines(false);
    sheet.SetShowRowColumnHeaders(false);
    sheet.SetShowZeros(false);
    sheet.SetRightToLeft(true);
    sheet.SetZoom(85);

    EXPECT_EQ(Color::FromArgb(255, 34, 68, 102), sheet.GetTabColor());
    EXPECT_FALSE(sheet.GetShowGridlines());
    EXPECT_FALSE(sheet.GetShowRowColumnHeaders());
    EXPECT_FALSE(sheet.GetShowZeros());
    EXPECT_TRUE(sheet.GetRightToLeft());
    EXPECT_EQ(85, sheet.GetZoom());

    sheet.SetTabColor(Color::Empty());
    EXPECT_EQ(Color::Empty(), sheet.GetTabColor());
    EXPECT_THROW(sheet.SetZoom(9), CellsException);
    EXPECT_THROW(sheet.SetZoom(401), CellsException);
}