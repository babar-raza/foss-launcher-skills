TEST_F(SlidesIntegrationTest, RemoveSlideByRef) {
    Presentation pres;
    auto* layout = &pres.layout_slides()[0];
    pres.slides().add_empty_slide(layout);
    EXPECT_EQ(pres.slides().size(), 2);
    pres.slides().remove(pres.slides()[1]);
    EXPECT_EQ(pres.slides().size(), 1);
}