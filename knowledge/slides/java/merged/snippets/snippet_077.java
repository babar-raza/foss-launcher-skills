@Test
    void testMultipleAuthors() {
        try (Presentation pres = new Presentation()) {
            pres.getCommentAuthors().addAuthor("Alice", "A");
            pres.getCommentAuthors().addAuthor("Bob", "B");
            assertThat(pres.getCommentAuthors().size()).isEqualTo(2);
        }
    }