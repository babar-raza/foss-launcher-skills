TEST(OpenXmlFeatureGoldenTests, data_validations_roundtrip_and_emit_expected_markup)
{
    TempDir temp("golden-validations");
    const auto path = temp.Path("validations.xlsx");
    auto workbook = CreateValidationWorkbook();
    workbook.Save(path.string());

    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");
    EXPECT_TRUE(Contains(worksheetXml, "<dataValidations"));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"list\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"decimal\""));
    EXPECT_TRUE(Contains(worksheetXml, "type=\"custom\""));
    EXPECT_TRUE(Contains(worksheetXml, "sqref=\"A1:A3\""));
    EXPECT_TRUE(Contains(worksheetXml, "sqref=\"B2:C3 E2:E3\""));
    EXPECT_TRUE(Contains(worksheetXml, "showDropDown=\"1\""));
    EXPECT_TRUE(Contains(worksheetXml, "<formula1>\"Open,Closed\"</formula1>"));
    EXPECT_TRUE(Contains(worksheetXml, "<formula2>9.5</formula2>"));

    Workbook loaded(path.string());
    AssertValidations(loaded);
}