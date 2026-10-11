TEST_F(TextIntegrationTest, AddTextFrame) {
    Presentation pres;
    auto& shape = pres.slides()[0].shapes().add_auto_shape(
        ShapeType::RECTANGLE, 50, 50, 300, 100, false);
    shape.add_text_frame("via add_text_frame");
    EXPECT_EQ(shape.text_frame()->text(), "via add_text_frame");
}