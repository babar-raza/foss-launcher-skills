TEST_F(TableIntegrationTest, TableStyleOptions) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    std::vector<double> col_widths = {120, 120};
    std::vector<double> row_heights = {40, 40, 40};
    auto& table = slide.shapes().add_table(50, 50, col_widths, row_heights);
    table.set_first_row(true);
    table.set_horizontal_banding(true);
    table.set_vertical_banding(false);

    auto pres2 = save_and_reopen(pres);
    auto* t2 = find_table(pres2.slides()[0]);
    ASSERT_NE(t2, nullptr);
    EXPECT_TRUE(t2->first_row());
    EXPECT_TRUE(t2->horizontal_banding());
}