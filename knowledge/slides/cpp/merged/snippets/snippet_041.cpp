TEST_F(PresentationIntegrationTest, CreateEmpty) {
    Presentation pres;
    EXPECT_EQ(pres.slides().size(), 1u);
}