TEST_F(ShapesIntegrationTest, ReorderShapes) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 100);
    auto& ellipse = slide.shapes().add_auto_shape(ShapeType::ELLIPSE, 300, 50, 150, 150);
    slide.shapes().reorder(0, ellipse);
    EXPECT_EQ(slide.shapes()[0].shape_type(), ShapeType::ELLIPSE);
}