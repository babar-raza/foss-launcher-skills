TEST(CompatibilityTests, worksheet_view_members_follow_supported_patterns)
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
}