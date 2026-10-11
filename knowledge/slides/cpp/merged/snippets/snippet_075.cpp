TEST_F(TableIntegrationTest, ColumnWidth) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    std::vector<double> col_widths = {100, 200, 300};
    std::vector<double> row_heights = {40};
    auto& table = slide.shapes().add_table(50, 50, col_widths, row_heights);
    EXPECT_EQ(table.columns()[0].width(), 100);
    EXPECT_EQ(table.columns()[1].width(), 200);
    EXPECT_EQ(table.columns()[2].width(), 300);
}