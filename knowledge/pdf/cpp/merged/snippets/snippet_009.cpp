TEST(AnnotationCollectionSmoke, DeleteVariants) {
    Ann a1, a2, a3;
    AnnotationCollection c;
    c.Add(a1); c.Add(a2); c.Add(a3);

    c.Delete(1);            // index-based
    EXPECT_EQ(c.Count(), 2);
    EXPECT_EQ(&c[0], &a1);
    EXPECT_EQ(&c[1], &a3);

    c.Delete(a3);           // value-based
    EXPECT_EQ(c.Count(), 1);
    EXPECT_EQ(&c[0], &a1);

    c.Delete();             // all
    EXPECT_EQ(c.Count(), 0);
}