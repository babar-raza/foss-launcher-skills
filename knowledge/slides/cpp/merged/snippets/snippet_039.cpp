TEST_F(NotesSlideIntegrationTest, NotesParentSlide) {
    Presentation pres;
    auto& slide = pres.slides()[0];
    auto* notes = slide.notes_slide_manager().add_notes_slide();
    ASSERT_NE(notes, nullptr);
    EXPECT_EQ(notes->parent_slide(), &slide);
}