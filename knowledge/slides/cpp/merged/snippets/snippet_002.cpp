TEST_F(CommentsIntegrationTest, AddComment) {
    Presentation pres;
    auto& author = pres.comment_authors().add_author("Alice", "A");
    auto& slide = pres.slides()[0];
    auto now = make_time(2026, 1, 15, 12, 0, 0);
    auto& comment =
        author.comments().add_comment("Review note", slide, PointF(2.0f, 3.0f), now);
    EXPECT_EQ(comment.text(), "Review note");
    EXPECT_EQ(comment.author()->name(), "Alice");

    // Round-trip: save, close, reopen.
    auto pres2 = save_and_reopen(pres);
    auto& a2 = pres2.comment_authors()[0];
    ASSERT_EQ(a2.comments().size(), 1);
    auto& c = a2.comments()[0];
    EXPECT_EQ(c.text(), "Review note");
}