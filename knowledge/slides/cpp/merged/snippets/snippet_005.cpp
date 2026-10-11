TEST_F(CommentsIntegrationTest, RemoveComment) {
    Presentation pres;
    auto& author = pres.comment_authors().add_author("Alice", "A");
    auto& slide = pres.slides()[0];
    auto now = std::chrono::system_clock::now();

    author.comments().add_comment("C1", slide, PointF(1, 1), now);
    author.comments().add_comment("C2", slide, PointF(2, 2), now);
    author.comments().add_comment("C3", slide, PointF(3, 3), now);
    ASSERT_EQ(author.comments().size(), 3);

    author.comments().remove_at(1);
    ASSERT_EQ(author.comments().size(), 2);

    // Round-trip: save, close, reopen.
    auto pres2 = save_and_reopen(pres);
    EXPECT_EQ(pres2.comment_authors()[0].comments().size(), 2);
}