TEST(WorkbookPortingTests, RowsColumnsAndMergesRoundTrip)
{
    TempDir temp;
    const auto path = temp.Path("layout.xlsx");

    Workbook workbook;
    auto& cells = workbook.GetWorksheets()[0].GetCells();
    cells["B2"].PutValue(std::string_view("merged"));
    cells.GetRows()[1].SetHeight(22.5);
    cells.GetRows()[3].SetIsHidden(true);
    cells.GetColumns()[1].SetWidth(18.25);
    cells.GetColumns()[2].SetIsHidden(true);
    cells.Merge(1, 1, 2, 3);
    workbook.Save(path.string());

    Workbook loaded(path.string());
    auto& loadedCells = loaded.GetWorksheets()[0].GetCells();
    EXPECT_EQ("merged", loadedCells["B2"].GetStringValue());
    ASSERT_TRUE(loadedCells.GetRows()[1].GetHeight().has_value());
    EXPECT_DOUBLE_EQ(22.5, *loadedCells.GetRows()[1].GetHeight());
    EXPECT_TRUE(loadedCells.GetRows()[3].GetIsHidden());
    ASSERT_TRUE(loadedCells.GetColumns()[1].GetWidth().has_value());
    EXPECT_DOUBLE_EQ(18.25, *loadedCells.GetColumns()[1].GetWidth());
    EXPECT_TRUE(loadedCells.GetColumns()[2].GetIsHidden());
    auto merged = loadedCells.GetMergedCells();
    ASSERT_EQ(1u, merged.size());
    EXPECT_EQ(1, merged[0].GetFirstRow());
    EXPECT_EQ(1, merged[0].GetFirstColumn());
    EXPECT_EQ(2, merged[0].GetTotalRows());
    EXPECT_EQ(3, merged[0].GetTotalColumns());
}