TEST(CommentsIntegrationTestNoFixture, InsertComment) {
    Presentation pres;
    auto& author = pres.comment_authors().add_author("Alice", "A");
    auto& slide = pres.slides()[0];
    auto now = std::chrono::system_clock::now();

    author.comments().add_comment("First", slide, PointF(1, 1), now);
    author.comments().add_comment("Third", slide, PointF(1, 3), now);
    author.comments().insert_comment(1, "Second", slide, PointF(1, 2), now);

    ASSERT_EQ(author.comments().size(), 3);
    EXPECT_EQ(author.comments()[1].text(), "Second");
}