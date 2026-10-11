TEST_F(ThreeDFormatIntegrationTest, DepthAndMaterial) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 100, 100, 200, 100);
    auto& tdf = shape.three_d_format();
    tdf.set_depth(20);
    tdf.set_material(MaterialPresetType::METAL);

    auto pres2 = save_and_reopen(pres);
    auto& tdf2 = pres2.slides()[0].shapes()[0].three_d_format();
    EXPECT_EQ(tdf2.depth(), 20);
    EXPECT_EQ(tdf2.material(), MaterialPresetType::METAL);
}