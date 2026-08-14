TEST(AnnotationFlagsEnum, BitwiseComposition) {
    auto f = AnnotationFlags::Print | AnnotationFlags::ReadOnly;
    EXPECT_EQ(static_cast<int>(f), 4 | 64);
    EXPECT_EQ(static_cast<int>(f & AnnotationFlags::Print),
              static_cast<int>(AnnotationFlags::Print));
    f &= ~AnnotationFlags::Print;
    EXPECT_EQ(static_cast<int>(f),
              static_cast<int>(AnnotationFlags::ReadOnly));
}