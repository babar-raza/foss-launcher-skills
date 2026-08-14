TEST_F(TableIntegrationTest, CreateTable) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    std::vector<double> col_widths = {100, 150, 200};
    std::vector<double> row_heights = {40, 40, 40};
    auto& table = slide.shapes().add_table(50, 50, col_widths, row_heights);
    EXPECT_EQ(table.rows().size(), 3);
    EXPECT_EQ(table.columns().size(), 3);
}