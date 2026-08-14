TEST_F(SlidesIntegrationTest, SlideName) {
    Presentation pres;
    pres.slides()[0].set_name("MySlide");
    EXPECT_EQ(pres.slides()[0].name(), "MySlide");

    auto pres2 = save_and_reopen(pres);
    EXPECT_EQ(pres2.slides()[0].name(), "MySlide");
}