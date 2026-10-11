TEST(CompatibilityTests, worksheet_protection_members_follow_supported_patterns)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];

    sheet.Protect();
    sheet.GetProtection().SetObjects(true);
    sheet.GetProtection().SetScenarios(true);
    sheet.GetProtection().SetAutoFilter(true);
    sheet.GetProtection().SetSelectLockedCells(true);
    sheet.GetProtection().SetSelectUnlockedCells(true);

    EXPECT_TRUE(sheet.GetProtection().GetIsProtected());
    EXPECT_TRUE(sheet.GetProtection().GetObjects());
    EXPECT_TRUE(sheet.GetProtection().GetScenarios());
    EXPECT_TRUE(sheet.GetProtection().GetAutoFilter());
    EXPECT_TRUE(sheet.GetProtection().GetSelectLockedCells());
    EXPECT_TRUE(sheet.GetProtection().GetSelectUnlockedCells());
}