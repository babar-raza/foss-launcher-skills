TEST_F(FillFormatIntegrationTest, PatternFill) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 100);
    shape.fill_format().set_fill_type(FillType::PATTERN);
    auto& pf = shape.fill_format().pattern_format();
    pf.set_pattern_style(PatternStyle::PERCENT50);
    pf.fore_color().set_color(Color::dark_blue);
    pf.back_color().set_color(Color::light_yellow);

    auto pres2 = save_and_reopen(pres);
    auto& ff2 = pres2.slides()[0].shapes()[0].fill_format();
    EXPECT_EQ(ff2.fill_type(), FillType::PATTERN);
    EXPECT_EQ(ff2.pattern_format().pattern_style(), PatternStyle::PERCENT50);
}