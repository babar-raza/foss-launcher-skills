TEST_F(SlidesIntegrationTest, InsertEmptySlide) {
    Presentation pres;
    auto* layout = &pres.layout_slides()[0];
    pres.slides().add_empty_slide(layout);
    pres.slides().insert_empty_slide(1, layout);
    EXPECT_EQ(pres.slides().size(), 3);
}