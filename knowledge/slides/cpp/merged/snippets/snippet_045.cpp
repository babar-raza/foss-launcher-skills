TEST_F(PresentationIntegrationTest, FirstSlideNumber) {
    Presentation pres;
    pres.set_first_slide_number(5);
    EXPECT_EQ(pres.first_slide_number(), 5);

    auto pres2 = save_and_reopen(pres);
    EXPECT_EQ(pres2.first_slide_number(), 5);
}