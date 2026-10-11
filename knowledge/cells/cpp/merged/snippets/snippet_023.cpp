TEST(CellDataGoldenTests, xlsx_roundtrip_mixed_scalar_cells_stream)
{
    auto workbook = CreateMixedCellWorkbook();
    std::vector<std::uint8_t> stream;
    workbook.Save(stream, SaveFormat::Xlsx);

    Workbook loaded(stream);
    AssertMixedWorkbook(loaded, false);
}