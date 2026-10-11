TEST_F(PresentationIntegrationTest, SlideCountAfterAdd) {
    Presentation pres;
    auto* layout = dynamic_cast<ILayoutSlide*>(&pres.layout_slides()[0]);
    ASSERT_NE(layout, nullptr);
    pres.slides().add_empty_slide(layout);
    EXPECT_EQ(pres.slides().size(), 2u);
}