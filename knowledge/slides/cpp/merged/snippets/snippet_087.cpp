TEST_F(TextIntegrationTest, ParagraphText) {
    Presentation pres;
    auto& shape = pres.slides()[0].shapes().add_auto_shape(
        ShapeType::RECTANGLE, 50, 50, 300, 100);
    shape.text_frame()->set_text("Original");
    auto& para = shape.text_frame()->paragraphs()[0];
    EXPECT_EQ(para.text(), "Original");
    para.set_text("Modified");
    EXPECT_EQ(para.text(), "Modified");
}