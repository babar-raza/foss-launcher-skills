TEST(ActionsSmoke, SubmitFormAction) {
    SubmitFormAction a;
    EXPECT_EQ(a.Flags(), 0);
    a.Flags(4);
    a.Url(FileSpecification{"https://example.org/submit"});
    EXPECT_EQ(a.Flags(), 4);
    EXPECT_EQ(a.Url().Name(), "https://example.org/submit");
}