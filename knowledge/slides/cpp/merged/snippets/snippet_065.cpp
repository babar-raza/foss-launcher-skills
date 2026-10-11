TEST_F(SlidesIntegrationTest, SlideLayoutAccess) {
    Presentation pres;
    EXPECT_NE(pres.slides()[0].layout_slide(), nullptr);
}