TEST(AnnotationCollectionSmoke, AddAndAccess) {
    Ann a1, a2, a3;
    AnnotationCollection c;
    c.Add(a1);
    c.Add(a2);
    c.Add(a3, /*considerRotation=*/true);
    EXPECT_EQ(c.Count(), 3);
    EXPECT_EQ(&c[0], &a1);
    EXPECT_EQ(&c[1], &a2);
    EXPECT_EQ(&c[2], &a3);
}