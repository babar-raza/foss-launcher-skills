TEST_F(TextIntegrationTest, TextPersists) {
    Presentation pres;
    pres.slides()[0].shapes().clear();
    auto& shape = pres.slides()[0].shapes().add_auto_shape(
        ShapeType::RECTANGLE, 50, 50, 300, 100);
    shape.text_frame()->set_text("Persistent text");

    auto pres2 = save_and_reopen(pres);
    auto& reloaded_shape = dynamic_cast<AutoShape&>(pres2.slides()[0].shapes()[0]);
    EXPECT_EQ(reloaded_shape.text_frame()->text(), "Persistent text");
}