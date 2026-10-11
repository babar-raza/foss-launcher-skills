@Test
    void testRemoveAuthor() throws IOException {
        try (var pres = new Presentation()) {
            pres.getCommentAuthors().addAuthor("Alice", "A");
            pres.getCommentAuthors().addAuthor("Bob", "B");
            pres.getCommentAuthors().remove(pres.getCommentAuthors().get(0));
            assertThat(pres.getCommentAuthors().size()).isEqualTo(1);

            try (var pres2 = saveAndReopen(pres)) {
                assertThat(pres2.getCommentAuthors().size()).isEqualTo(1);
                assertThat(pres2.getCommentAuthors().get(0).getName()).isEqualTo("Bob");
            }
        }
    }