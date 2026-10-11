TEST(CommentsIntegrationTestNoFixture, GetSlideComments) {
    Presentation pres;
    auto& a1 = pres.comment_authors().add_author("Alice", "A");
    auto& a2 = pres.comment_authors().add_author("Bob", "B");
    auto& slide = pres.slides()[0];
    auto now = std::chrono::system_clock::now();

    a1.comments().add_comment("Alice's", slide, PointF(1, 1), now);
    a2.comments().add_comment("Bob's", slide, PointF(2, 2), now);

    auto all_c = slide.get_slide_comments(nullptr);
    EXPECT_EQ(all_c.size(), 2);

    auto bob_c = slide.get_slide_comments(&a2);
    ASSERT_EQ(bob_c.size(), 1);
    EXPECT_EQ(bob_c[0]->text(), "Bob's");
}