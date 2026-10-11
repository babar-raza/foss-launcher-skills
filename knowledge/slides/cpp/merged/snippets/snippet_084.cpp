TEST_F(TextIntegrationTest, TextFrameText) {
    Presentation pres;
    auto& shape = pres.slides()[0].shapes().add_auto_shape(
        ShapeType::RECTANGLE, 50, 50, 300, 100);
    shape.text_frame()->set_text("Hello, World!");
    EXPECT_EQ(shape.text_frame()->text(), "Hello, World!");
}