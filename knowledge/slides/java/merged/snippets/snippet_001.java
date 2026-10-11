@Test
    void aReplyMustBeRecordedInTheFileAsAReply() throws Exception {
        Path out = writeCommentAndReply();

        try (PptxPackage pkg = PptxPackage.open(out)) {
            List<String> threadedParts = pkg.entryNames().stream()
                    .filter(name -> name.startsWith("ppt/threadedComments/"))
                    .toList();
            assertThat(threadedParts)
                    .as("threaded-comment parts in %s; parts present are %s",
                            out, pkg.entryNames())
                    .isNotEmpty();

            assertThat(PackageAssertions.contentTypeOverrides(pkg).values())
                    .as("content type declared for the threaded-comment part in %s", out)
                    .contains(THREADED_COMMENTS_CONTENT_TYPE);

            assertThat(PackageAssertions.selectNodes(
                    pkg, threadedParts.get(0), "//p188:cm[@parentId]"))
                    .as("threaded comments carrying a parent id in %s", out)
                    .isNotEmpty();
        }
    }