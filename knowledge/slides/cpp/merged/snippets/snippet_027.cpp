TEST_F(FillFormatIntegrationTest, NoFill) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 100);
    shape.fill_format().set_fill_type(FillType::NO_FILL);

    auto pres2 = save_and_reopen(pres);
    EXPECT_EQ(pres2.slides()[0].shapes()[0].fill_format().fill_type(), FillType::NO_FILL);
}