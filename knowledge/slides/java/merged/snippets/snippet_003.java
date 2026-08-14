@Test
    void testAddAuthor() throws IOException {
        try (var pres = new Presentation()) {
            ICommentAuthor author = pres.getCommentAuthors().addAuthor("Alice", "A");
            assertThat(author.getName()).isEqualTo("Alice");
            assertThat(author.getInitials()).isEqualTo("A");
            assertThat(pres.getCommentAuthors().size()).isEqualTo(1);

            try (var pres2 = saveAndReopen(pres)) {
                assertThat(pres2.getCommentAuthors().size()).isEqualTo(1);
                assertThat(pres2.getCommentAuthors().get(0).getName()).isEqualTo("Alice");
                assertThat(pres2.getCommentAuthors().get(0).getInitials()).isEqualTo("A");
            }
        }
    }