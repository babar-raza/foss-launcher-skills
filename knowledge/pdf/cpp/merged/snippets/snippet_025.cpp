TEST(AnnotationTypeEnum, RepresentativeValues) {
    EXPECT_EQ(static_cast<int>(AnnotationType::Text),           0);
    EXPECT_EQ(static_cast<int>(AnnotationType::Link),           13);
    EXPECT_EQ(static_cast<int>(AnnotationType::Highlight),      7);
    EXPECT_EQ(static_cast<int>(AnnotationType::FreeText),       6);
    EXPECT_EQ(static_cast<int>(AnnotationType::FileAttachment), 15);
    EXPECT_EQ(static_cast<int>(AnnotationType::Watermark),      20);
}