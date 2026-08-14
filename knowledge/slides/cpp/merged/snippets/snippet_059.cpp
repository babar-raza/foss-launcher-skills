TEST_F(SlidesIntegrationTest, AddEmptySlide) {
    Presentation pres;
    auto* layout = &pres.layout_slides()[0];
    pres.slides().add_empty_slide(layout);
    EXPECT_EQ(pres.slides().size(), 2);
}