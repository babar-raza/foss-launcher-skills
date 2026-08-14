TEST(AnnotationCollectionSmoke, DeleteByValueIsNoopWhenAbsent) {
    Ann a1, a2;
    AnnotationCollection c;
    c.Add(a1);
    c.Delete(a2);   // a2 not in collection — no-op
    EXPECT_EQ(c.Count(), 1);
    EXPECT_TRUE(c.Contains(a1));
}