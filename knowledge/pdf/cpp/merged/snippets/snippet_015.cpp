TEST(AnnotationLoadOnOpen, ReadOnlyResaveIsLossless) {
    const std::string out = TmpPath("loss1");
    const std::string out2 = TmpPath("loss2");
    MakeThreeAnnotPdf(out);

    {
        Document re{out};
        ASSERT_EQ(re.Pages()[1].Annotations().Count(), 3);
        re.Save(out2);  // no changes
    }

    Document re2{out2};
    auto& a2 = re2.Pages()[1].Annotations();
    EXPECT_EQ(a2.Count(), 3);
    EXPECT_EQ(a2[0].Contents(), "note one");
    std::filesystem::remove(out);
    std::filesystem::remove(out2);
}