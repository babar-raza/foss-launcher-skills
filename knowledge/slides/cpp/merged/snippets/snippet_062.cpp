TEST_F(SlidesIntegrationTest, RemoveSlideAt) {
    Presentation pres;
    auto* layout = &pres.layout_slides()[0];
    pres.slides().add_empty_slide(layout);
    pres.slides().remove_at(1);
    EXPECT_EQ(pres.slides().size(), 1);
}