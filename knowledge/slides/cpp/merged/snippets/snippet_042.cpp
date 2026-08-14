TEST_F(PresentationIntegrationTest, SaveAndReload) {
    Presentation pres;
    auto pres2 = save_and_reopen(pres);
    EXPECT_EQ(pres2.slides().size(), 1u);
}