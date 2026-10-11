@Test
    void testAddComment() throws IOException {
        try (var pres = new Presentation()) {
            ICommentAuthor author = pres.getCommentAuthors().addAuthor("Alice", "A");
            ISlide slide = pres.getSlides().get(0);
            LocalDateTime now = LocalDateTime.of(2026, 1, 15, 12, 0, 0);
            IComment comment = author.getComments().addComment("Review note", slide,
                    new PointF(2.0f, 3.0f), now);
            assertThat(comment.getText()).isEqualTo("Review note");
            assertThat(comment.getAuthor().getName()).isEqualTo("Alice");

            try (var pres2 = saveAndReopen(pres)) {
                ICommentAuthor a2 = pres2.getCommentAuthors().get(0);
                assertThat(a2.getComments().size()).isEqualTo(1);
                assertThat(a2.getComments().get(0).getText()).isEqualTo("Review note");
            }
        }
    }