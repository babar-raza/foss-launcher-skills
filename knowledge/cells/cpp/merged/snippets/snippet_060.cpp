TEST(WorkbookMetadataUnitTests, workbook_metadata_apis_mutate_expected_settings)
{
    auto workbook = CreateWorkbookMetadataWorkbook();
    AssertWorkbookMetadata(workbook);
}