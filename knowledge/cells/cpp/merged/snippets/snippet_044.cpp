TEST(WorkbookMetadataGoldenTests, workbook_metadata_loads_from_root_relationship_targets)
{
    TempDir temp("golden-workbook-metadata-root-relationships");
    const auto path = temp.Path("workbook-metadata-root-targets.xlsx");
    auto workbook = CreateWorkbookMetadataWorkbook();
    workbook.Save(path.string());

    Package::MoveEntry(path, "docProps/core.xml", "metadata/core-props.xml");
    Package::MoveEntry(path, "docProps/app.xml", "metadata/app-props.xml");
    RewriteDocumentPropertiesTargets(path, "/metadata/core-props.xml", "/metadata/app-props.xml");

    Workbook loaded(path.string());
    AssertWorkbookMetadata(loaded);
}