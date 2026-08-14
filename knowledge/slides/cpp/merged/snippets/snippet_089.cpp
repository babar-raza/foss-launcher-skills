TEST_F(TextIntegrationTest, AddPortion) {
    Presentation pres;
    auto& shape = pres.slides()[0].shapes().add_auto_shape(
        ShapeType::RECTANGLE, 50, 50, 400, 100);
    shape.text_frame()->set_text("Hello ");
    Portion new_portion("World!");
    shape.text_frame()->paragraphs()[0].portions().add(std::move(new_portion));
    EXPECT_NE(shape.text_frame()->text().find("World!"), std::string::npos);
}