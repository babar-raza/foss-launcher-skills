@Test
    void unrelatedCommentsMustNotCarryAThreadingExtension() throws Exception {
        Path out = tempDir.resolve("comments-unrelated.pptx");
        try (var pres = new Presentation()) {
            ICommentAuthor author = pres.getCommentAuthors().addAuthor("Jane Smith", "JS");
            ISlide slide = pres.getSlides().get(0);
            author.getComments().addComment("First", slide,
                    new PointF(1.0f, 1.0f), LocalDateTime.now());
            author.getComments().addComment("Second", slide,
                    new PointF(2.0f, 2.0f), LocalDateTime.now());
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            String part = "ppt/comments/comment1.xml";
            assertThat(PackageAssertions.selectNodes(pkg, part, "//p:cm/p:extLst"))
                    .as("extension lists on unrelated comments in %s of %s%n%s",
                            part, out, pkg.text(part))
                    .isEmpty();
        }
    }