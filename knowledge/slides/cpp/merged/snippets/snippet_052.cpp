TEST_F(ShapesIntegrationTest, RemoveShape) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    auto& s = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 100);
    slide.shapes().add_auto_shape(ShapeType::ELLIPSE, 300, 50, 150, 150);
    EXPECT_EQ(slide.shapes().size(), 2);
    slide.shapes().remove(s);
    EXPECT_EQ(slide.shapes().size(), 1);
}