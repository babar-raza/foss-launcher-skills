@Test
    void aCommentMustNotCarryAnAttributeTheStandardDoesNotDefine() throws Exception {
        Path out = writeCommentAndReply();

        try (PptxPackage pkg = PptxPackage.open(out)) {
            for (String partName : pkg.entryNames()) {
                if (!partName.startsWith("ppt/comments/")) {
                    continue;
                }
                assertThat(pkg.text(partName))
                        .as("part %s of %s", partName, out)
                        .doesNotContain("parentCmId");
            }
        }
    }