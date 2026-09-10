@Test
    void testGetSlideComments() {
        try (Presentation pres = new Presentation()) {
            ICommentAuthor a1 = pres.getCommentAuthors().addAuthor("Alice", "A");
            ICommentAuthor a2 = pres.getCommentAuthors().addAuthor("Bob", "B");
            ISlide slide = pres.getSlides().get(0);
            LocalDateTime now = LocalDateTime.now();
            a1.getComments().addComment("Alice's", slide, new PointF(1, 1), now);
            a2.getComments().addComment("Bob's", slide, new PointF(2, 2), now);

            IComment[] allComments = slide.getSlideComments(null);
            assertThat(allComments).hasSize(2);

            IComment[] bobComments = slide.getSlideComments(a2);
            assertThat(bobComments).hasSize(1);
            assertThat(bobComments[0].getText()).isEqualTo("Bob's");
        }
    }