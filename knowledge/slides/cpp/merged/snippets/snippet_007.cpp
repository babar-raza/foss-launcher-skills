TEST(CommentsIntegrationTestNoFixture, ClearComments) {
    Presentation pres;
    auto& author = pres.comment_authors().add_author("Alice", "A");
    auto& slide = pres.slides()[0];
    auto now = std::chrono::system_clock::now();

    author.comments().add_comment("C1", slide, PointF(1, 1), now);
    author.comments().add_comment("C2", slide, PointF(2, 2), now);
    author.comments().clear();
    EXPECT_EQ(author.comments().size(), 0);
}