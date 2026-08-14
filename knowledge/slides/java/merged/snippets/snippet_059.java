@Test
    void testNotesHeaderFooter() throws IOException {
        try (var pres = new Presentation()) {
            var notes = pres.getSlides().get(0).getNotesSlideManager().addNotesSlide();
            notes.getNotesTextFrame().setText("Notes");
            var hfm = notes.getHeaderFooterManager();
            hfm.setFooterVisibility(true);
            hfm.setFooterText("Confidential");
            hfm.setSlideNumberVisibility(true);

            assertThat(hfm.isFooterVisible()).isTrue();
            assertThat(hfm.isSlideNumberVisible()).isTrue();

            try (var pres2 = saveAndReopen(pres)) {
                var ns2 = pres2.getSlides().get(0).getNotesSlideManager().getNotesSlide();
                var hfm2 = ns2.getHeaderFooterManager();
                assertThat(hfm2.isFooterVisible()).isTrue();
                assertThat(hfm2.isSlideNumberVisible()).isTrue();
            }
        }
    }