TEST_F(PresentationIntegrationTest, SaveToFile) {
    Presentation pres;
    auto path = (tmp_dir_ / "output.pptx").string();
    pres.save(path, SaveFormat::PPTX);
    EXPECT_GT(std::filesystem::file_size(path), 0u);
}