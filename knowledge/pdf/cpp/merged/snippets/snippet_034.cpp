TEST(AnnotationSmoke, RectAndDimensionAccessors) {
    Rectangle r{10.0, 20.0, 30.0, 50.0, false};
    Ann a{r};
    EXPECT_NEAR(a.Width(),  20.0, kEps);
    EXPECT_NEAR(a.Height(), 30.0, kEps);
    EXPECT_NEAR(a.Rect().LLX(), 10.0, kEps);

    a.Width(40.0);
    EXPECT_NEAR(a.Rect().URX(), 50.0, kEps);
    a.Height(15.0);
    EXPECT_NEAR(a.Rect().URY(), 35.0, kEps);
}