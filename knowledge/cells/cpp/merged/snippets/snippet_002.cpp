TEST(CompatibilityTests, save_overloads_produce_equivalent_workbooks)
{
    TempDir temp("compat-save-overloads");
    const auto filePath = temp.Path("book-file.xlsx");
    auto workbook = CreateMixedCellWorkbook();
    workbook.Save(filePath.string(), SaveFormat::Xlsx);

    std::vector<std::uint8_t> stream;
    workbook.Save(stream, SaveFormat::Xlsx);

    Workbook fromFile(filePath.string());
    Workbook fromStream(stream);
    AssertWorkbookDataEquals(fromFile, fromStream);
}