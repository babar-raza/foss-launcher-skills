TEST(AttachmentLoadOnOpen, RoundTripCountAndExtract) {
    const auto src = Tmp("src.bin");
    const auto out = Tmp("attached.pdf");
    const std::string payload = "embedded attachment payload \x01\x02\xFF end";
    MakeAttachedPdf(out, src, payload);

    Document re{out.string()};
    ASSERT_EQ(re.EmbeddedFiles().Count(), 1);

    PdfExtractor ex{re};
    auto names = ex.GetAttachNames();
    ASSERT_EQ(names.size(), 1u);

    const auto extracted = Tmp("extracted.bin");
    ex.GetAttachment(extracted.string());  // first attachment
    EXPECT_EQ(ReadFile(extracted), payload);

    std::filesystem::remove(src);
    std::filesystem::remove(out);
    std::filesystem::remove(extracted);
}