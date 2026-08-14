TEST_F(NotesSlideIntegrationTest, AddNotes) {
    Presentation pres;
    auto& slide = pres.slides()[0];
    auto* notes = slide.notes_slide_manager().add_notes_slide();
    ASSERT_NE(notes, nullptr);
    notes->notes_text_frame().set_text("Speaker notes");

    auto pres2 = save_and_reopen(pres);
    auto* ns2 = pres2.slides()[0].notes_slide_manager().notes_slide();
    ASSERT_NE(ns2, nullptr);
    EXPECT_EQ(ns2->notes_text_frame().text(), "Speaker notes");
}