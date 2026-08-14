TEST_F(NotesSlideIntegrationTest, RemoveNotes) {
    Presentation pres;
    auto& mgr = pres.slides()[0].notes_slide_manager();
    mgr.add_notes_slide();
    ASSERT_NE(mgr.notes_slide(), nullptr);

    mgr.remove_notes_slide();
    EXPECT_EQ(mgr.notes_slide(), nullptr);

    auto pres2 = save_and_reopen(pres);
    EXPECT_EQ(pres2.slides()[0].notes_slide_manager().notes_slide(), nullptr);
}