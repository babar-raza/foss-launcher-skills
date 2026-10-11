@Test
    void testClearComments() {
        try (Presentation pres = new Presentation()) {
            ICommentAuthor author = pres.getCommentAuthors().addAuthor("Alice", "A");
            ISlide slide = pres.getSlides().get(0);
            LocalDateTime now = LocalDateTime.now();
            author.getComments().addComment("C1", slide, new PointF(1, 1), now);
            author.getComments().addComment("C2", slide, new PointF(2, 2), now);
            author.getComments().clear();
            assertThat(author.getComments().size()).isEqualTo(0);
        }
    }