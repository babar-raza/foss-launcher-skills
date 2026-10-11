@Test
    void openingAndSavingADeckMustLoseNoPartOfIt() throws Exception {
        Path source = Fixtures.authoredDeck(tempDir, "authored.pptx", "First", "Second", "Third");

        Path out = tempDir.resolve("round-tripped.pptx");
        try (var pres = new Presentation(source.toString())) {
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage before = PptxPackage.open(source);
             PptxPackage after = PptxPackage.open(out)) {
            var lost = new ArrayList<>(before.entryNames());
            lost.removeAll(after.entryNames());
            assertThat(lost)
                    .as("parts of %s that did not survive being saved to %s; the file had %d "
                            + "parts and now has %d", source, out,
                            before.entryNames().size(), after.entryNames().size())
                    .isEmpty();

            var added = new ArrayList<>(after.entryNames());
            added.removeAll(before.entryNames());
            assertThat(added)
                    .as("parts in %s that %s did not have; the file had %d parts and now has %d",
                            out, source,
                            before.entryNames().size(), after.entryNames().size())
                    .isEmpty();
        }
    }