TEST_F(ShapesIntegrationTest, IterateShapes) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 100);
    slide.shapes().add_auto_shape(ShapeType::ELLIPSE, 300, 50, 150, 150);
    std::vector<Shape*> shapes;
    for (auto& s : slide.shapes()) {
        shapes.push_back(&*s);
    }
    EXPECT_EQ(shapes.size(), 2);
}