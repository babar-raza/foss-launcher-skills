TEST(AnnotationCollectionSmoke, DefaultIsEmpty) {
    AnnotationCollection c;
    EXPECT_EQ(c.Count(), 0);
    EXPECT_FALSE(c.IsReadOnly());
}