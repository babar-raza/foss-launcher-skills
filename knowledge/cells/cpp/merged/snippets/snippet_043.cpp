TEST(WorkbookMetadataGoldenTests, extended_document_properties_do_not_inject_default_application_metadata)
{
    TempDir temp("golden-extended-document-properties-no-default-app");
    const auto path = temp.Path("document-properties-no-default-app.xlsx");
    Workbook workbook;
    workbook.GetDocumentProperties().SetCompany("Aspose Cells FOSS");
    workbook.GetDocumentProperties().SetManager("Release");
    workbook.Save(path.string());

    const auto appXml = Package::ReadEntryText(path, "docProps/app.xml");
    EXPECT_TRUE(Contains(appXml, "<Company>Aspose Cells FOSS</Company>"));
    EXPECT_TRUE(Contains(appXml, "<Manager>Release</Manager>"));
    EXPECT_FALSE(Contains(appXml, "<Application>"));
    EXPECT_FALSE(Contains(appXml, "<AppVersion>"));

    Workbook loaded(path.string());
    EXPECT_EQ("Aspose Cells FOSS", loaded.GetDocumentProperties().GetCompany());
    EXPECT_EQ("Release", loaded.GetDocumentProperties().GetManager());
    EXPECT_EQ("", loaded.GetDocumentProperties().GetExtended().GetApplication());
    EXPECT_EQ("", loaded.GetDocumentProperties().GetExtended().GetAppVersion());
}