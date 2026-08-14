TEST(CompatibilityTests, exception_mapping_uses_cells_exception_types)
{
    EXPECT_THROW(static_cast<void>(Workbook().GetWorksheets()["missing"]), CellsException);
    EXPECT_THROW(static_cast<void>(Workbook().GetWorksheets()[0].GetCells()["1A"]), CellsException);
    EXPECT_THROW(static_cast<void>(Workbook(std::vector<std::uint8_t>{1, 2, 3, 4})), InvalidFileFormatException);
}