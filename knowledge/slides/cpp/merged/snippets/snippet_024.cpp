TEST_F(FillFormatIntegrationTest, SolidFill) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 100);
    shape.fill_format().set_fill_type(FillType::SOLID);
    shape.fill_format().solid_fill_color().set_color(
        Color::from_argb(255, 0, 128, 255));

    auto pres2 = save_and_reopen(pres);
    auto& ff = pres2.slides()[0].shapes()[0].fill_format();
    EXPECT_EQ(ff.fill_type(), FillType::SOLID);
    auto c = ff.solid_fill_color().color();
    EXPECT_EQ(c.r(), 0);
    EXPECT_EQ(c.g(), 128);
    EXPECT_EQ(c.b(), 255);
}