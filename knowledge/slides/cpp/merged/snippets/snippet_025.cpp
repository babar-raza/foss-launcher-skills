TEST_F(FillFormatIntegrationTest, GradientFill) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 300, 150);
    shape.fill_format().set_fill_type(FillType::GRADIENT);
    auto& gf = shape.fill_format().gradient_format();
    gf.set_gradient_shape(GradientShape::LINEAR);
    gf.set_linear_gradient_angle(45);
    gf.gradient_stops().add(0.0f, Color::blue);
    gf.gradient_stops().add(1.0f, Color::red);

    auto pres2 = save_and_reopen(pres);
    auto& ff2 = pres2.slides()[0].shapes()[0].fill_format();
    EXPECT_EQ(ff2.fill_type(), FillType::GRADIENT);
    EXPECT_GE(ff2.gradient_format().gradient_stops().size(), 2u);
}