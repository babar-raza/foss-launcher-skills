TEST_F(PresentationIntegrationTest, RaiiDestruction) {
    {
        Presentation pres;
        EXPECT_GE(pres.slides().size(), 1u);
    }
    // Object destroyed without explicit dispose — should not crash.
}