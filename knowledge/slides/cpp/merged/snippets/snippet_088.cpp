TEST_F(TextIntegrationTest, PortionsCount) {
    Presentation pres;
    auto& shape = pres.slides()[0].shapes().add_auto_shape(
        ShapeType::RECTANGLE, 50, 50, 300, 100);
    shape.text_frame()->set_text("Hello");
    EXPECT_GE(shape.text_frame()->paragraphs()[0].portions().count(), 1u);
}