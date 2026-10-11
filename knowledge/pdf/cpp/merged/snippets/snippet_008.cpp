TEST(AnnotationCollectionSmoke, ContainsAndRemove) {
    Ann a1, a2;
    AnnotationCollection c;
    c.Add(a1);
    EXPECT_TRUE(c.Contains(a1));
    EXPECT_FALSE(c.Contains(a2));

    EXPECT_TRUE(c.Remove(a1));
    EXPECT_FALSE(c.Contains(a1));
    EXPECT_FALSE(c.Remove(a1));  // already gone
    EXPECT_EQ(c.Count(), 0);
}