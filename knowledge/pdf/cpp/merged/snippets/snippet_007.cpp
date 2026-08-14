TEST(AnnotationCollectionSmoke, IndexOutOfRangeThrows) {
    AnnotationCollection c;
    Ann a;
    c.Add(a);
    EXPECT_THROW(c[1], std::out_of_range);
    EXPECT_THROW(c[-1], std::out_of_range);
    EXPECT_THROW(c.Delete(2), std::out_of_range);
}