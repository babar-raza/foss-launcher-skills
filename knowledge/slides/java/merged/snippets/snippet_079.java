@Test
    void testRemoveComment() throws IOException {
        try (var pres = new Presentation()) {
            ICommentAuthor author = pres.getCommentAuthors().addAuthor("Alice", "A");
            ISlide slide = pres.getSlides().get(0);
            LocalDateTime now = LocalDateTime.now();
            author.getComments().addComment("C1", slide, new PointF(1, 1), now);
            author.getComments().addComment("C2", slide, new PointF(2, 2), now);
            author.getComments().addComment("C3", slide, new PointF(3, 3), now);
            assertThat(author.getComments().size()).isEqualTo(3);

            author.getComments().removeAt(1);
            assertThat(author.getComments().size()).isEqualTo(2);

            try (var pres2 = saveAndReopen(pres)) {
                assertThat(pres2.getCommentAuthors().get(0).getComments().size()).isEqualTo(2);
            }
        }
    }