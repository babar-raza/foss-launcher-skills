TEST_F(NotesSlideIntegrationTest, NotesSize) {
    Presentation pres;
    auto& ns = pres.notes_size();
    EXPECT_GT(ns.size().width, 0.0f);
    EXPECT_GT(ns.size().height, 0.0f);
}