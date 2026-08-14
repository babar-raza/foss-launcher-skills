TEST(CellDataUnitTests, worksheet_name_and_collection_guards)
{
    Workbook workbook;
    workbook.GetWorksheets().Add("Data");

    EXPECT_THROW(workbook.GetWorksheets().Add("data"), CellsException);
    EXPECT_THROW(static_cast<void>(workbook.GetWorksheets()[0].GetCells()["1A"]), CellsException);
    EXPECT_THROW(static_cast<void>(workbook.GetWorksheets()[0].GetCells()(-1, 0)), CellsException);

    auto parsed = Core::CellAddress::Parse("AB3");
    EXPECT_EQ(2, parsed.GetRowIndex());
    EXPECT_EQ(27, parsed.GetColumnIndex());
    EXPECT_EQ("AB3", parsed.ToString());
}