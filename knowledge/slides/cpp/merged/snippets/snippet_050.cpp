TEST_F(ShapesIntegrationTest, MultipleShapeTypes) {
    std::vector<ShapeType> types = {ShapeType::RECTANGLE, ShapeType::ELLIPSE, ShapeType::TRIANGLE};
    Presentation pres;
    auto& slide = blank_slide(pres);
    for (auto st : types) {
        auto& s = slide.shapes().add_auto_shape(st, 10, 10, 100, 100);
        EXPECT_EQ(s.shape_type(), st);
    }
    EXPECT_EQ(slide.shapes().size(), 3);
}