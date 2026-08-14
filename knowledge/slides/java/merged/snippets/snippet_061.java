@Test
    void testNotesSize() {
        try (var pres = new Presentation()) {
            var ns = pres.getNotesSize();
            assertThat(ns.getSize().getWidth()).isGreaterThan(0);
            assertThat(ns.getSize().getHeight()).isGreaterThan(0);
        }
    }