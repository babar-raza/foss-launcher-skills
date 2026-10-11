TEST_F(CommentsIntegrationTest, RemoveAuthor) {
    Presentation pres;
    pres.comment_authors().add_author("Alice", "A");
    pres.comment_authors().add_author("Bob", "B");
    pres.comment_authors().remove(pres.comment_authors()[0]);
    ASSERT_EQ(pres.comment_authors().size(), 1);

    // Round-trip: save, close, reopen.
    auto pres2 = save_and_reopen(pres);
    ASSERT_EQ(pres2.comment_authors().size(), 1);
    EXPECT_EQ(pres2.comment_authors()[0].name(), "Bob");
}