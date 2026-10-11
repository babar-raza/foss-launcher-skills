TEST(WorkbookMetadataGoldenTests, unreferenced_document_properties_parts_are_ignored)
{
    TempDir temp("golden-workbook-metadata-orphaned-docprops");
    const auto path = temp.Path("workbook-metadata-orphaned-docprops.xlsx");
    auto workbook = CreateWorkbookMetadataWorkbook();
    workbook.Save(path.string());

    RemoveDocumentPropertiesRelationships(path);

    Workbook loaded(path.string());
    EXPECT_EQ("WorkbookCode", loaded.GetProperties().GetCodeName());
    AssertDocumentPropertiesAreDefault(loaded);
}