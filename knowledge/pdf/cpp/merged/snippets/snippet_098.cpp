TEST(CellsSmoke, AddOverloadsAndIndexer) {
    Cells cells;
    EXPECT_EQ(cells.Count(), 0);

    cells.Add();
    cells.Add("hello");
    Cell& styled = cells.Add("world");
    styled.Alignment(HorizontalAlignment::Right);

    ASSERT_EQ(cells.Count(), 3);
    // 1-based indexer returns the same stored cells.
    EXPECT_EQ(cells[3].Alignment(), HorizontalAlignment::Right);

    cells.RemoveRange(1, 1);  // drop the first empty cell
    EXPECT_EQ(cells.Count(), 2);
}