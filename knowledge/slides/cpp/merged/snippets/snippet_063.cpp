TEST_F(SlidesIntegrationTest, SlideHidden) {
    Presentation pres;
    pres.slides()[0].set_hidden(true);
    EXPECT_TRUE(pres.slides()[0].hidden());

    auto pres2 = save_and_reopen(pres);
    EXPECT_TRUE(pres2.slides()[0].hidden());
}