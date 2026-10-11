TEST(AttachmentLoadOnOpen, ReadOnlyResaveIsLossless) {
    const auto src = Tmp("src3.bin");
    const auto out = Tmp("attached3.pdf");
    const auto out2 = Tmp("resaved3.pdf");
    const std::string payload = "stable payload 123";
    MakeAttachedPdf(out, src, payload);

    {
        Document re{out.string()};
        ASSERT_EQ(re.EmbeddedFiles().Count(), 1);
        re.Save(out2.string());  // no changes
    }

    Document re2{out2.string()};
    ASSERT_EQ(re2.EmbeddedFiles().Count(), 1);
    PdfExtractor ex{re2};
    const auto extracted = Tmp("extracted3.bin");
    ex.GetAttachment(extracted.string());
    EXPECT_EQ(ReadFile(extracted), payload);

    std::filesystem::remove(src);
    std::filesystem::remove(out);
    std::filesystem::remove(out2);
    std::filesystem::remove(extracted);
}