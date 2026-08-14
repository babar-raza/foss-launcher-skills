TEST_F(NotesSlideIntegrationTest, NotesHeaderFooter) {
    Presentation pres;
    auto* notes = pres.slides()[0].notes_slide_manager().add_notes_slide();
    ASSERT_NE(notes, nullptr);
    notes->notes_text_frame().set_text("Notes");
    auto& hfm = notes->header_footer_manager();
    hfm.set_footer_visibility(true);
    hfm.set_footer_text("Confidential");
    hfm.set_slide_number_visibility(true);

    EXPECT_TRUE(hfm.is_footer_visible());
    EXPECT_TRUE(hfm.is_slide_number_visible());

    auto pres2 = save_and_reopen(pres);
    auto* ns2 = pres2.slides()[0].notes_slide_manager().notes_slide();
    ASSERT_NE(ns2, nullptr);
    auto& hfm2 = ns2->header_footer_manager();
    EXPECT_TRUE(hfm2.is_footer_visible());
    EXPECT_TRUE(hfm2.is_slide_number_visible());
}