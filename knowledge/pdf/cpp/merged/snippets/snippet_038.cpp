TEST(AttachmentLoadOnOpen, DeleteAllOnDiskClears) {
    const auto src = Tmp("src2.bin");
    const auto out = Tmp("attached2.pdf");
    const auto out2 = Tmp("cleared2.pdf");
    MakeAttachedPdf(out, src, "to be removed");

    {
        Document re{out.string()};
        ASSERT_EQ(re.EmbeddedFiles().Count(), 1);
        re.EmbeddedFiles().Delete();  // remove all
        EXPECT_EQ(re.EmbeddedFiles().Count(), 0);
        re.Save(out2.string());
    }

    Document re2{out2.string()};
    EXPECT_EQ(re2.EmbeddedFiles().Count(), 0);

    std::filesystem::remove(src);
    std::filesystem::remove(out);
    std::filesystem::remove(out2);
}