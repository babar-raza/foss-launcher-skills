@Test
    void noSlideMayReferToARelationshipItDoesNotDeclare() throws Exception {
        Path out = writeDeckWithPicture("dangling.pptx", Files.readAllBytes(PNG));
        try (PptxPackage pkg = PptxPackage.open(out)) {
            PackageAssertions.assertEveryRelationshipReferenceResolves(pkg);
        }
    }