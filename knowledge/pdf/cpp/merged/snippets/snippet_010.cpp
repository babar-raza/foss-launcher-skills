TEST(AnnotationCollectionSmoke, Clear) {
    Ann a1, a2;
    AnnotationCollection c;
    c.Add(a1); c.Add(a2);
    c.Clear();
    EXPECT_EQ(c.Count(), 0);
    EXPECT_FALSE(c.Contains(a1));
}