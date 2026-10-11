TEST(WorkbookPortingTests, SaveFileCreatesReadableOpenXmlPackage)
{
    TempDir temp;
    const auto path = temp.Path("created.xlsx");

    Workbook workbook;
    PopulateBasicWorkbook(workbook);
    SaveOptions options;
    options.SetUseSharedStrings(true);
    workbook.Save(path.string(), options);

    ASSERT_TRUE(std::filesystem::exists(path));
    auto bytes = ReadAllBytes(path);
    ASSERT_GT(bytes.size(), 100u);

    EXPECT_NE(std::string::npos, ReadZipText(bytes, "[Content_Types].xml").find("spreadsheetml.sheet.main+xml"));
    EXPECT_NE(std::string::npos, ReadZipText(bytes, "xl/workbook.xml").find("Data"));
    EXPECT_NE(std::string::npos, ReadZipText(bytes, "xl/worksheets/sheet1.xml").find("B1"));
    EXPECT_NE(std::string::npos, ReadZipText(bytes, "xl/sharedStrings.xml").find("alpha"));
}