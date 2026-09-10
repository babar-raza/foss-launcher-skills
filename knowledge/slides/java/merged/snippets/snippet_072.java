@Test
    void anExpandingInternalEntityMustBeRefused() throws Exception {
        Path source = Fixtures.authoredDeck(tempDir, "source.pptx", "First");
        Path poisoned = tempDir.resolve("expanding.pptx");
        ZipSurgery.copyWithReplacement(source, poisoned, "ppt/slides/slide1.xml", xml -> {
            String doctype = "<!DOCTYPE p:sld ["
                    + "<!ENTITY a \"aaaaaaaaaa\">"
                    + "<!ENTITY b \"&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;\">"
                    + "<!ENTITY c \"&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;\">"
                    + "]>";
            int afterDeclaration = xml.indexOf("?>") + 2;
            return xml.substring(0, afterDeclaration) + doctype + xml.substring(afterDeclaration);
        });

        assertThatThrownBy(() -> {
            try (var pres = new Presentation(poisoned.toString())) {
                pres.getSlides().size();
            }
        }).as("opening %s, whose ppt/slides/slide1.xml declares nested internal entities", poisoned)
                .isInstanceOf(RuntimeException.class);
    }