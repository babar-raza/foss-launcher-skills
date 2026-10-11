TEST_F(TextFormattingIntegrationTest, ParagraphAlignment) {
    Presentation pres;
    pres.slides()[0].shapes().clear();
    auto& shape = pres.slides()[0].shapes().add_auto_shape(
        ShapeType::RECTANGLE, 50, 50, 400, 200);
    shape.text_frame()->set_text("Centered");
    shape.text_frame()->paragraphs()[0].paragraph_format().set_alignment(
        TextAlignment::CENTER);

    auto pres2 = save_and_reopen(pres);
    auto& reloaded = dynamic_cast<AutoShape&>(pres2.slides()[0].shapes()[0]);
    auto& pf = reloaded.text_frame()->paragraphs()[0].paragraph_format();
    EXPECT_EQ(pf.alignment(), TextAlignment::CENTER);
}