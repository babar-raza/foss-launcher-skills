TEST_F(CommentsIntegrationTest, AddAuthor) {
    Presentation pres;
    auto& author = pres.comment_authors().add_author("Alice", "A");
    EXPECT_EQ(author.name(), "Alice");
    EXPECT_EQ(author.initials(), "A");
    EXPECT_EQ(pres.comment_authors().size(), 1);

    // Round-trip: save, close, reopen.
    auto pres2 = save_and_reopen(pres);
    ASSERT_EQ(pres2.comment_authors().size(), 1);
    EXPECT_EQ(pres2.comment_authors()[0].name(), "Alice");
    EXPECT_EQ(pres2.comment_authors()[0].initials(), "A");
}