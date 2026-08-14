TEST(CompatibilityTests, file_and_stream_load_paths_produce_same_values)
{
    TempDir temp("compat-load-paths");
    const auto path = temp.Path("book.xlsx");
    auto workbook = CreateMixedCellWorkbook();
    workbook.Save(path.string());

    auto bytes = ReadAllBytes(path);
    Workbook fromFile(path.string());
    Workbook fromStream(bytes);
    AssertWorkbookDataEquals(fromFile, fromStream);
}