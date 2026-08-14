@Test
    void testAddNotes() throws IOException {
        try (var pres = new Presentation()) {
            var slide = pres.getSlides().get(0);
            var notes = slide.getNotesSlideManager().addNotesSlide();
            notes.getNotesTextFrame().setText("Speaker notes");

            try (var pres2 = saveAndReopen(pres)) {
                var ns2 = pres2.getSlides().get(0).getNotesSlideManager().getNotesSlide();
                assertThat(ns2).isNotNull();
                assertThat(ns2.getNotesTextFrame().getText()).isEqualTo("Speaker notes");
            }
        }
    }