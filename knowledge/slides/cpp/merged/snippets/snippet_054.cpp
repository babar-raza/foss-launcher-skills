TEST_F(ShapesIntegrationTest, ClearShapes) {
    Presentation pres;
    auto& slide = pres.slides()[0];
    slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 100);
    slide.shapes().clear();
    EXPECT_EQ(slide.shapes().size(), 0);
}