@Test
    void removingSpeakerNotesMustNotLeaveTheNotesPartDeclared() throws Exception {
        Path withNotes = tempDir.resolve("with-notes.pptx");
        try (var pres = new Presentation()) {
            pres.getSlides().get(0).getNotesSlideManager().addNotesSlide()
                    .getNotesTextFrame().setText("Speaker notes go here.");
            pres.save(withNotes.toString(), SaveFormat.PPTX);
        }

        Path removed = tempDir.resolve("notes-removed.pptx");
        try (var pres = new Presentation(withNotes.toString())) {
            pres.getSlides().get(0).getNotesSlideManager().removeNotesSlide();
            pres.save(removed.toString(), SaveFormat.PPTX);
        }

        assertNothingRefersToAMissingPart(removed);
        ThirdPartyReadBack.assertOpens(removed);
    }