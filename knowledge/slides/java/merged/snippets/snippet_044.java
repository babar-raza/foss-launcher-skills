@Test
    void removingTheLastCommentMustNotLeaveTheCommentsPartDeclared() throws Exception {
        Path withComment = tempDir.resolve("with-comment.pptx");
        try (var pres = new Presentation()) {
            ICommentAuthor author = pres.getCommentAuthors().addAuthor("Jane Smith", "JS");
            author.getComments().addComment("Review this slide", pres.getSlides().get(0),
                    new PointF(2.0f, 2.0f), LocalDateTime.now());
            pres.save(withComment.toString(), SaveFormat.PPTX);
        }

        Path removed = tempDir.resolve("comment-removed.pptx");
        try (var pres = new Presentation(withComment.toString())) {
            pres.getCommentAuthors().get(0).getComments().removeAt(0);
            pres.save(removed.toString(), SaveFormat.PPTX);
        }

        assertNothingRefersToAMissingPart(removed);
        ThirdPartyReadBack.assertOpens(removed);
    }