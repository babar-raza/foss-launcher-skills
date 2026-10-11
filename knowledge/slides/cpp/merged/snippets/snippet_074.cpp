TEST_F(TableIntegrationTest, RowHeight) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    std::vector<double> col_widths = {200};
    std::vector<double> row_heights = {30, 50, 70};
    auto& table = slide.shapes().add_table(50, 50, col_widths, row_heights);
    EXPECT_EQ(table.rows()[0].height(), 30);
    EXPECT_EQ(table.rows()[1].height(), 50);
    EXPECT_EQ(table.rows()[2].height(), 70);
}