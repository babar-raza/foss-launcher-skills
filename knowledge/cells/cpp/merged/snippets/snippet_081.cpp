TEST(WorkbookPortingTests, WorkbookSettingsAndDocumentPropertiesRoundTrip)
{
    TempDir temp;
    const auto path = temp.Path("metadata.xlsx");

    Workbook workbook;
    workbook.GetSettings().SetDate1904(true);
    workbook.GetDocumentProperties().SetTitle("Quarterly Summary");
    workbook.GetDocumentProperties().SetAuthor("Automation");
    workbook.GetDocumentProperties().SetCompany("Aspose.Cells.FOSS Tests");
    workbook.Save(path.string());

    auto bytes = ReadAllBytes(path);
    EXPECT_NE(std::string::npos, ReadZipText(bytes, "xl/workbook.xml").find("date1904=\"1\""));
    EXPECT_NE(std::string::npos, ReadZipText(bytes, "docProps/core.xml").find("Quarterly Summary"));
    EXPECT_NE(std::string::npos, ReadZipText(bytes, "docProps/app.xml").find("Aspose.Cells.FOSS Tests"));

    Workbook loaded(path.string());
    EXPECT_TRUE(loaded.GetSettings().GetDate1904());
    EXPECT_EQ("Quarterly Summary", loaded.GetDocumentProperties().GetTitle());
    EXPECT_EQ("Automation", loaded.GetDocumentProperties().GetAuthor());
    EXPECT_EQ("Aspose.Cells.FOSS Tests", loaded.GetDocumentProperties().GetCompany());
}