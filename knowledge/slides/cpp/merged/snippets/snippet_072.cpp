TEST_F(TableIntegrationTest, CellBorders) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    std::vector<double> col_widths = {150};
    std::vector<double> row_heights = {50};
    auto& table = slide.shapes().add_table(50, 50, col_widths, row_heights);
    auto& cell = table.rows()[0][0];
    cell.text_frame()->set_text("Bordered");
    auto& fmt = cell.cell_format();

    fmt.border_top().fill_format().set_fill_type(FillType::SOLID);
    fmt.border_top().fill_format().solid_fill_color().set_color(Drawing::Color::red);
    fmt.border_top().set_width(3);

    fmt.border_bottom().fill_format().set_fill_type(FillType::SOLID);
    fmt.border_bottom().fill_format().solid_fill_color().set_color(Drawing::Color::red);
    fmt.border_bottom().set_width(3);

    fmt.border_left().fill_format().set_fill_type(FillType::SOLID);
    fmt.border_left().fill_format().solid_fill_color().set_color(Drawing::Color::red);
    fmt.border_left().set_width(3);

    fmt.border_right().fill_format().set_fill_type(FillType::SOLID);
    fmt.border_right().fill_format().solid_fill_color().set_color(Drawing::Color::red);
    fmt.border_right().set_width(3);

    auto pres2 = save_and_reopen(pres);
    auto* t2 = find_table(pres2.slides()[0]);
    ASSERT_NE(t2, nullptr);
    auto& fmt2 = t2->rows()[0][0].cell_format();
    EXPECT_EQ(fmt2.border_top().width(), 3);
}