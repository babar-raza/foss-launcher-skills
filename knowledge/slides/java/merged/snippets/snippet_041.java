private void assertTextBodiesCarryAParagraph(Path out) throws Exception {
        try (PptxPackage pkg = PptxPackage.open(out)) {
            List<Element> bodies = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//p:txBody");
            assertThat(bodies)
                    .as("text bodies in slide 1 of %s", out)
                    .isNotEmpty();
            for (Element body : bodies) {
                assertThat(PackageAssertions.childNames(body))
                        .as("children of a <p:txBody> in slide 1 of %s%n%s",
                                out, pkg.text("ppt/slides/slide1.xml"))
                        .contains("a:p");
            }
        }
    }