TEST_F(ShapesIntegrationTest, RemoveAt) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 100);
    slide.shapes().add_auto_shape(ShapeType::ELLIPSE, 300, 50, 150, 150);
    slide.shapes().remove_at(0);
    EXPECT_EQ(slide.shapes().size(), 1);
}