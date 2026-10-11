@Test
    void theClassicCommentListMustCarryTheThreadOnTheReply() throws Exception {
        Path out = writeCommentAndReply();

        try (PptxPackage pkg = PptxPackage.open(out)) {
            String part = "ppt/comments/comment1.xml";
            List<Element> comments =
                    PackageAssertions.selectNodes(pkg, part, "//p:cmLst/p:cm");
            assertThat(comments)
                    .as("classic comments in %s of %s%n%s", part, out, pkg.text(part))
                    .hasSize(2);

            Element parent = comments.get(0);
            Element reply = comments.get(1);

            assertThat(PackageAssertions.selectNodes(pkg, part,
                    "//p:cm[@idx='" + parent.getAttribute("idx") + "']"
                            + "/p:extLst/p:ext/p15:threadingInfo"))
                    .as("the comment that starts the thread must not claim a parent, in %s of %s"
                            + "%n%s", part, out, pkg.text(part))
                    .isEmpty();

            List<Element> parentRefs = PackageAssertions.selectNodes(pkg, part,
                    THREADING_INFO + "/p15:parentCm");
            assertThat(parentRefs)
                    .as("p15:parentCm on the reply in %s of %s%n%s", part, out, pkg.text(part))
                    .hasSize(1);
            assertThat(parentRefs.get(0).getAttribute("authorId"))
                    .as("p15:parentCm/@authorId in %s of %s", part, out)
                    .isEqualTo(parent.getAttribute("authorId"));
            assertThat(parentRefs.get(0).getAttribute("idx"))
                    .as("p15:parentCm/@idx in %s of %s", part, out)
                    .isEqualTo(parent.getAttribute("idx"));

            assertThat(PackageAssertions.childNames(reply))
                    .as("children of the replying <p:cm> in %s of %s", part, out)
                    .containsExactly("p:pos", "p:text", "p:extLst");
        }
    }