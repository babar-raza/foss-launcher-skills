TEST(CommentsIntegrationTestNoFixture, MultipleAuthors) {
    Presentation pres;
    pres.comment_authors().add_author("Alice", "A");
    pres.comment_authors().add_author("Bob", "B");
    EXPECT_EQ(pres.comment_authors().size(), 2);
}