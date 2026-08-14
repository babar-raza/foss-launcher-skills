TEST(CompatibilityTests, file_and_stream_roundtrip_preserve_styles)
{
    TempDir temp("compat-styles");
    const auto filePath = temp.Path("styled-file.xlsx");
    auto workbook = CreateStyledWorkbook();
    workbook.Save(filePath.string());

    std::vector<std::uint8_t> stream;
    workbook.Save(stream, SaveFormat::Xlsx);

    Workbook fromFile(filePath.string());
    Workbook fromStream(stream);
    AssertPrimaryStyle(fromFile.GetWorksheets()[0].GetCells()["A1"].GetStyle());
    AssertPrimaryStyle(fromStream.GetWorksheets()[0].GetCells()["A1"].GetStyle());
    AssertCustomNumberStyle(fromFile.GetWorksheets()[0].GetCells()["B2"].GetStyle());
    AssertCustomNumberStyle(fromStream.GetWorksheets()[0].GetCells()["B2"].GetStyle());
    EXPECT_EQ(CellValueType::Blank, fromFile.GetWorksheets()[0].GetCells()["B2"].GetType());
    EXPECT_EQ(CellValueType::Blank, fromStream.GetWorksheets()[0].GetCells()["B2"].GetType());
}