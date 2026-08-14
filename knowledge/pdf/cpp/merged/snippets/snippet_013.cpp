TEST(AnnotationLoadOnOpen, DeleteOnDiskReducesCount) {
    const std::string out = TmpPath("del1");
    const std::string out2 = TmpPath("del2");
    MakeThreeAnnotPdf(out);

    {
        Document re{out};
        auto& annots = re.Pages()[1].Annotations();
        ASSERT_EQ(annots.Count(), 3);
        annots.Delete(1);  // drop the Square (index 1)
        EXPECT_EQ(annots.Count(), 2);
        re.Save(out2);
    }

    Document re2{out2};
    auto& a2 = re2.Pages()[1].Annotations();
    EXPECT_EQ(a2.Count(), 2);
    EXPECT_EQ(a2[0].AnnotationType(), AnnotationType::Text);
    EXPECT_EQ(a2[1].AnnotationType(), AnnotationType::Circle);
    std::filesystem::remove(out);
    std::filesystem::remove(out2);
}