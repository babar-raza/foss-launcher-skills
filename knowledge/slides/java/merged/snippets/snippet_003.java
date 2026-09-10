@Test
    void aThreadMustSurviveALoadAndASaveUnchanged() throws Exception {
        Path first = writeCommentAndReply();
        Path second = tempDir.resolve("comment-reply-resaved.pptx");
        try (var pres = new Presentation(first.toString())) {
            pres.save(second.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(second)) {
            assertThat(PackageAssertions.selectNodes(pkg, "ppt/comments/comment1.xml",
                    THREADING_INFO + "/p15:parentCm"))
                    .as("p15:parentCm after a load and a save, in %s%n%s",
                            second, pkg.text("ppt/comments/comment1.xml"))
                    .hasSize(1);
            assertThat(PackageAssertions.selectNodes(pkg,
                    "ppt/threadedComments/threadedComment1.xml", "//p188:cm[@parentId]"))
                    .as("p188:cm/@parentId after a load and a save, in %s", second)
                    .hasSize(1);
        }
    }