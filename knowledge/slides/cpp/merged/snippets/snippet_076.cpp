TEST_F(TableIntegrationTest, CellFill) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    std::vector<double> col_widths = {200};
    std::vector<double> row_heights = {60};
    auto& table = slide.shapes().add_table(50, 50, col_widths, row_heights);
    auto& cell = table.rows()[0][0];
    cell.cell_format().fill_format().set_fill_type(FillType::SOLID);
    cell.cell_format().fill_format().solid_fill_color().set_color(Drawing::Color::light_blue);
    cell.text_frame()->set_text("Blue");

    auto pres2 = save_and_reopen(pres);
    auto* t2 = find_table(pres2.slides()[0]);
    ASSERT_NE(t2, nullptr);
    auto& cf2 = t2->rows()[0][0].cell_format();
    EXPECT_EQ(cf2.fill_format().fill_type(), FillType::SOLID);
}