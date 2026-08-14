TEST_F(PresentationIntegrationTest, LoadExisting) {
    auto path = (tmp_dir_ / "existing.pptx").string();
    {
        Presentation pres;
        pres.save(path, SaveFormat::PPTX);
    }
    Presentation pres(path);
    EXPECT_GE(pres.slides().size(), 1u);
}