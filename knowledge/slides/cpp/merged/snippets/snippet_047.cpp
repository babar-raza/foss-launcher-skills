TEST_F(PresentationIntegrationTest, DisposeIsIdempotent) {
    Presentation pres;
    pres.dispose();
    pres.dispose(); // second call should be harmless
}