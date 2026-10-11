TEST(CellDataGoldenTests, xlsx_roundtrip_mixed_scalar_cells_file)
{
    TempDir temp("golden-file");
    const auto path = temp.Path("mixed.xlsx");
    auto workbook = CreateMixedCellWorkbook();
    workbook.Save(path.string());

    Workbook loaded(path.string());
    AssertMixedWorkbook(loaded, false);
}