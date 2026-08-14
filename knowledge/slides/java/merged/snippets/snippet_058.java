@Test
    void testRemoveNotes() throws IOException {
        try (var pres = new Presentation()) {
            var mgr = pres.getSlides().get(0).getNotesSlideManager();
            mgr.addNotesSlide();
            assertThat(mgr.getNotesSlide()).isNotNull();

            mgr.removeNotesSlide();
            assertThat(mgr.getNotesSlide()).isNull();

            try (var pres2 = saveAndReopen(pres)) {
                assertThat(pres2.getSlides().get(0).getNotesSlideManager().getNotesSlide()).isNull();
            }
        }
    }