TEST(CompatibilityTests, workbook_metadata_members_follow_supported_patterns)
{
    auto workbook = CreateWorkbookMetadataWorkbook();
    AssertWorkbookMetadata(workbook);
    EXPECT_EQ("Data", workbook.GetWorksheets()[workbook.GetProperties().GetView().GetActiveTab()].GetName());
}