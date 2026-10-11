TEST(AnnotationSmoke, DefaultAccessors) {
    Ann a;
    EXPECT_EQ(a.AnnotationType(), AnnotationType::Text);
    EXPECT_EQ(a.Flags(), AnnotationFlags::Default);
    EXPECT_FALSE(a.UpdateAppearanceOnConvert());
    EXPECT_FALSE(a.UseFontSubset());
    EXPECT_TRUE(a.Contents().empty());
    EXPECT_TRUE(a.Name().empty());
    EXPECT_TRUE(a.ActiveState().empty());
    EXPECT_TRUE(a.FullName().empty());
    EXPECT_EQ(a.PageIndex(), 0);
    EXPECT_EQ(a.Alignment(), TextAlignment::Left);
    EXPECT_EQ(a.HorizontalAlignment(),
              Aspose::Pdf::HorizontalAlignment::None);
}