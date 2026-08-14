TEST(AnnotationLoadOnOpen, RoundTripCountTypesContents) {
    const std::string out = TmpPath("rt");
    MakeThreeAnnotPdf(out);

    Document re{out};
    auto& annots = re.Pages()[1].Annotations();
    ASSERT_EQ(annots.Count(), 3);

    // Subtypes and contents survive (order preserved).
    EXPECT_EQ(annots[0].AnnotationType(), AnnotationType::Text);
    EXPECT_EQ(annots[0].Contents(), "note one");
    EXPECT_EQ(annots[1].AnnotationType(), AnnotationType::Square);
    EXPECT_EQ(annots[1].Contents(), "box two");
    EXPECT_EQ(annots[2].AnnotationType(), AnnotationType::Circle);
    std::filesystem::remove(out);
}