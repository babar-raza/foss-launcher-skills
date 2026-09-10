private Path deckWithExternalEntity(Path target) throws Exception {
        Path source = Fixtures.authoredDeck(tempDir, "source.pptx", PLACEHOLDER);
        Path poisoned = tempDir.resolve("poisoned.pptx");
        String uri = target.toUri().toString();
        Path result = ZipSurgery.copyWithReplacement(source, poisoned, "ppt/slides/slide1.xml",
                xml -> {
                    String doctype =
                            "<!DOCTYPE p:sld [<!ENTITY disclose SYSTEM \"" + uri + "\">]>";
                    int afterDeclaration = xml.indexOf("?>") + 2;
                    // The entity has to be referenced as well as declared, or the parser has no
                    // reason to fetch anything and the test would pass for the wrong reason.
                    return xml.substring(0, afterDeclaration) + doctype
                            + xml.substring(afterDeclaration).replace(PLACEHOLDER, "&disclose;");
                });
        try (PptxPackage pkg = PptxPackage.open(result)) {
            assertThat(pkg.text("ppt/slides/slide1.xml"))
                    .as("the poisoned package must declare the entity and reference it, or the "
                            + "parser has no reason to fetch anything and the test would pass for "
                            + "the wrong reason")
                    .contains("<!DOCTYPE")
                    .contains("&disclose;");
        }
        return result;
    }