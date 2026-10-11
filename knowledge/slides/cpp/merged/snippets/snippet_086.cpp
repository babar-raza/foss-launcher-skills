TEST_F(TextIntegrationTest, ParagraphsCount) {
    Presentation pres;
    auto& shape = pres.slides()[0].shapes().add_auto_shape(
        ShapeType::RECTANGLE, 50, 50, 300, 100);
    shape.text_frame()->set_text("Line");
    EXPECT_GE(shape.text_frame()->paragraphs().size(), 1u);
}