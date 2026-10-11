TEST_F(ShapesIntegrationTest, InsertAutoShape) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 100);
    slide.shapes().add_auto_shape(ShapeType::ELLIPSE, 300, 50, 150, 150);
    slide.shapes().insert_auto_shape(1, ShapeType::TRIANGLE, 150, 200, 100, 100);
    EXPECT_EQ(slide.shapes().size(), 3);
}