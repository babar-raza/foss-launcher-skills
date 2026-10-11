TEST_F(SlidesIntegrationTest, IndexOf) {
    Presentation pres;
    auto* layout = &pres.layout_slides()[0];
    pres.slides().add_empty_slide(layout);
    EXPECT_EQ(pres.slides().index_of(pres.slides()[0]), 0);
    EXPECT_EQ(pres.slides().index_of(pres.slides()[1]), 1);
}