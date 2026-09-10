private Path writeCommentAndReply() throws IOException {
        Path out = tempDir.resolve("comment-reply.pptx");
        try (var pres = new Presentation()) {
            ICommentAuthor author = pres.getCommentAuthors().addAuthor("Jane Smith", "JS");
            ISlide slide = pres.getSlides().get(0);
            IComment parent = author.getComments().addComment("Review this slide", slide,
                    new PointF(2.0f, 2.0f), LocalDateTime.now());
            IComment reply = author.getComments().addComment("Agreed, will do", slide,
                    new PointF(2.5f, 2.5f), LocalDateTime.now());
            reply.setParentComment(parent);
            pres.save(out.toString(), SaveFormat.PPTX);
        }
        return out;
    }