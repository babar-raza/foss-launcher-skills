TEST(AnnotationFlagsEnum, BitfieldValues) {
    EXPECT_EQ(static_cast<int>(AnnotationFlags::Default),        0);
    EXPECT_EQ(static_cast<int>(AnnotationFlags::Invisible),      1);
    EXPECT_EQ(static_cast<int>(AnnotationFlags::Hidden),         2);
    EXPECT_EQ(static_cast<int>(AnnotationFlags::Print),          4);
    EXPECT_EQ(static_cast<int>(AnnotationFlags::NoZoom),         8);
    EXPECT_EQ(static_cast<int>(AnnotationFlags::ReadOnly),       64);
    EXPECT_EQ(static_cast<int>(AnnotationFlags::LockedContents), 512);
}