TEST_F(LineFormatIntegrationTest, LineColorAndWidth) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 100);
    auto& lf = shape.line_format();
    lf.set_width(5);
    lf.fill_format().set_fill_type(FillType::SOLID);
    lf.fill_format().solid_fill_color().set_color(Color::dark_red);

    auto pres2 = save_and_reopen(pres);
    auto& lf2 = pres2.slides()[0].shapes()[0].line_format();
    EXPECT_EQ(lf2.width(), 5);
    EXPECT_EQ(lf2.fill_format().fill_type(), FillType::SOLID);
    auto c = lf2.fill_format().solid_fill_color().color();
    EXPECT_EQ(c.r(), Color::dark_red.r());
}