private static void assertPictureIsReachable(Path pptx, String... acceptedExtensions)
            throws IOException {
        try (PptxPackage pkg = PptxPackage.open(pptx)) {
            List<Element> blips = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//p:pic/p:blipFill/a:blip");
            assertThat(blips).as("a:blip elements in slide 1 of %s", pptx).hasSize(1);

            String embedId = blips.get(0).getAttributeNS(PptxPackage.NS_REL, "embed");
            assertThat(embedId).as("r:embed of the blip in %s", pptx).isNotEmpty();

            List<Element> relationships = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/_rels/slide1.xml.rels",
                    "//rel:Relationship[@Id='" + embedId + "']");
            assertThat(relationships)
                    .as("relationship '%s' declared in ppt/slides/_rels/slide1.xml.rels of %s%n%s",
                            embedId, pptx, pkg.text("ppt/slides/_rels/slide1.xml.rels"))
                    .hasSize(1);

            String target = PptxPackage.resolveTarget(
                    "ppt/slides/slide1.xml", relationships.get(0).getAttribute("Target"));
            assertThat(pkg.hasPart(target))
                    .as("image part %s referenced from slide 1 of %s", target, pptx)
                    .isTrue();
            assertThat(PackageAssertions.contentTypeDefaults(pkg).keySet())
                    .as("content type registered for the image extension in %s", pptx)
                    .containsAnyElementsOf(List.of(acceptedExtensions));
        }
    }