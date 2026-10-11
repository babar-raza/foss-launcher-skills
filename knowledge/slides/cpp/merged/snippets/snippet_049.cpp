TEST_F(ShapesIntegrationTest, AddAutoShape) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 100);
    EXPECT_EQ(slide.shapes().size(), 1);
    EXPECT_EQ(shape.shape_type(), ShapeType::RECTANGLE);
}