TEST(AnnotationSmoke, BorderAccessIsLValueReference) {
    Ann a;
    a.Border().Width(5);
    EXPECT_EQ(a.Border().Width(), 5);

    Border b{nullptr};
    b.Style(BorderStyle::Inset);
    a.Border(b);
    EXPECT_EQ(a.Border().Style(), BorderStyle::Inset);
}