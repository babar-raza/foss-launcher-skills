TEST_F(TableIntegrationTest, CellText) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    std::vector<double> col_widths = {100, 100};
    std::vector<double> row_heights = {40, 40};
    auto& table = slide.shapes().add_table(50, 50, col_widths, row_heights);
    table.rows()[0][0].text_frame()->set_text("A");
    table.rows()[0][1].text_frame()->set_text("B");
    table.rows()[1][0].text_frame()->set_text("C");
    table.rows()[1][1].text_frame()->set_text("D");

    auto pres2 = save_and_reopen(pres);
    auto* t2 = find_table(pres2.slides()[0]);
    ASSERT_NE(t2, nullptr);
    EXPECT_EQ(t2->rows()[0][0].text_frame()->text(), "A");
    EXPECT_EQ(t2->rows()[0][1].text_frame()->text(), "B");
    EXPECT_EQ(t2->rows()[1][0].text_frame()->text(), "C");
    EXPECT_EQ(t2->rows()[1][1].text_frame()->text(), "D");
}