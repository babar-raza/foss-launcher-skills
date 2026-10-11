TEST(CellImageSmoke, BackgroundImageProperty) {
    Cell cell;
    EXPECT_TRUE(cell.BackgroundImage().empty());
    const std::vector<std::byte> bytes{std::byte{1}, std::byte{2}, std::byte{3}};
    cell.BackgroundImage(bytes);
    EXPECT_EQ(cell.BackgroundImage().size(), 3u);
}