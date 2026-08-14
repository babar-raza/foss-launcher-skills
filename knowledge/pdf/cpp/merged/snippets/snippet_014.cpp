TEST(AnnotationLoadOnOpen, DeleteAllOnDiskClears) {
    const std::string out = TmpPath("clr1");
    const std::string out2 = TmpPath("clr2");
    MakeThreeAnnotPdf(out);

    {
        Document re{out};
        auto& annots = re.Pages()[1].Annotations();
        ASSERT_EQ(annots.Count(), 3);
        annots.Delete();  // clear all
        EXPECT_EQ(annots.Count(), 0);
        re.Save(out2);
    }

    Document re2{out2};
    EXPECT_EQ(re2.Pages()[1].Annotations().Count(), 0);
    std::filesystem::remove(out);
    std::filesystem::remove(out2);
}