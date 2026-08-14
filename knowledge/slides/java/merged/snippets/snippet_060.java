@Test
    void testNotesParentSlide() {
        try (var pres = new Presentation()) {
            var slide = pres.getSlides().get(0);
            var notes = slide.getNotesSlideManager().addNotesSlide();
            assertThat(notes.getParentSlide()).isSameAs(slide);
        }
    }