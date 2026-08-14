TEST_F(TextIntegrationTest, OverwriteText) {
    Presentation pres;
    auto& shape = pres.slides()[0].shapes().add_auto_shape(
        ShapeType::RECTANGLE, 50, 50, 300, 100);
    shape.text_frame()->set_text("First");
    shape.text_frame()->set_text("Second");
    EXPECT_EQ(shape.text_frame()->text(), "Second");
}