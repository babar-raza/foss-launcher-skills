TEST(WorksheetFeatureUnitTests, worksheet_protection_apis_mutate_expected_settings)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];

    sheet.Protect();
    sheet.GetProtection().SetObjects(true);
    sheet.GetProtection().SetFormatCells(true);
    sheet.GetProtection().SetInsertRows(true);
    sheet.GetProtection().SetSelectUnlockedCells(true);

    EXPECT_TRUE(sheet.GetProtection().GetIsProtected());
    EXPECT_TRUE(sheet.GetProtection().GetObjects());
    EXPECT_TRUE(sheet.GetProtection().GetFormatCells());
    EXPECT_TRUE(sheet.GetProtection().GetInsertRows());
    EXPECT_TRUE(sheet.GetProtection().GetSelectUnlockedCells());

    sheet.Unprotect();
    EXPECT_FALSE(sheet.GetProtection().GetIsProtected());
    EXPECT_FALSE(sheet.GetProtection().GetObjects());
    EXPECT_FALSE(sheet.GetProtection().GetFormatCells());
    EXPECT_FALSE(sheet.GetProtection().GetInsertRows());
    EXPECT_FALSE(sheet.GetProtection().GetSelectUnlockedCells());

    sheet.GetProtection().SetAutoFilter(true);
    EXPECT_TRUE(sheet.GetProtection().GetIsProtected());
    EXPECT_TRUE(sheet.GetProtection().GetAutoFilter());
}