@Test
    void testInsertComment() {
        try (Presentation pres = new Presentation()) {
            ICommentAuthor author = pres.getCommentAuthors().addAuthor("Alice", "A");
            ISlide slide = pres.getSlides().get(0);
            LocalDateTime now = LocalDateTime.now();
            author.getComments().addComment("First", slide, new PointF(1, 1), now);
            author.getComments().addComment("Third", slide, new PointF(1, 3), now);
            author.getComments().insertComment(1, "Second", slide, new PointF(1, 2), now);
            assertThat(author.getComments().size()).isEqualTo(3);
            assertThat(author.getComments().get(1).getText()).isEqualTo("Second");
        }
    }