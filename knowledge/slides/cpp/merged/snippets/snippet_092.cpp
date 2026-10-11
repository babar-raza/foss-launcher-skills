TEST_F(ThreeDFormatIntegrationTest, BevelTop) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 100, 100, 200, 100);
    auto& tdf = shape.three_d_format();
    tdf.bevel_top().set_bevel_type(BevelPresetType::CIRCLE);
    tdf.bevel_top().set_width(10);
    tdf.bevel_top().set_height(5);

    auto pres2 = save_and_reopen(pres);
    auto& bt = pres2.slides()[0].shapes()[0].three_d_format().bevel_top();
    EXPECT_EQ(bt.bevel_type(), BevelPresetType::CIRCLE);
    EXPECT_EQ(bt.width(), 10);
    EXPECT_EQ(bt.height(), 5);
}