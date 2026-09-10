@Test
    void theMisspeltGraphicFrameLockingElementMustNotAppearAnywhere() throws Exception {
        Path out = writeDeckWithTable();

        try (PptxPackage pkg = PptxPackage.open(out)) {
            for (String partName : pkg.xmlPartNames()) {
                assertThat(pkg.text(partName))
                        .as("part %s of %s", partName, out)
                        .doesNotContain("graphicFrameLocking");
            }
        }
    }