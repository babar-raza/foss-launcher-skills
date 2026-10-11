TEST_F(TableIntegrationTest, MergeCells) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    std::vector<double> col_widths = {100, 100, 100};
    std::vector<double> row_heights = {40, 40};
    auto& table = slide.shapes().add_table(50, 50, col_widths, row_heights);
    auto& cell1 = table.rows()[0][0];
    auto& cell2 = table.rows()[0][1];
    table.merge_cells(cell1, cell2, false);
    EXPECT_TRUE(cell1.is_merged_cell());
    EXPECT_GE(cell1.col_span(), 2);

    auto pres2 = save_and_reopen(pres);
    auto* t2 = find_table(pres2.slides()[0]);
    ASSERT_NE(t2, nullptr);
    EXPECT_TRUE(t2->rows()[0][0].is_merged_cell());
}