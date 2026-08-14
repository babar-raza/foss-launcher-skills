TEST(WorkbookPortingTests, SaveAndLoadStreamRoundTrip)
{
    Workbook workbook;
    PopulateBasicWorkbook(workbook);
    std::vector<std::uint8_t> output;

    workbook.Save(output, SaveOptions());
    ASSERT_GT(output.size(), 100u);

    Workbook loaded(output);
    EXPECT_EQ("Data", loaded.GetWorksheets()[0].GetName());
    EXPECT_EQ("alpha", loaded.GetWorksheets()[0].GetCells()["A1"].GetStringValue());
    EXPECT_EQ(42, loaded.GetWorksheets()[0].GetCells()["B1"].GetValue().AsInteger());
}