TEST_F(ShapesIntegrationTest, ShapePersistsAfterReload) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 100);

    auto pres2 = save_and_reopen(pres);
    EXPECT_GE(pres2.slides()[0].shapes().size(), 1);
    EXPECT_EQ(pres2.slides()[0].shapes()[0].shape_type(), ShapeType::RECTANGLE);
}