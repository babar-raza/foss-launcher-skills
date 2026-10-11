@Test
    void packageRulesAcceptAKnownGoodDeck() throws IOException {
        Path good = Fixtures.authoredDeck(tempDir, "good.pptx", "One", "Two");
        try (PptxPackage pkg = PptxPackage.open(good)) {
            PackageAssertions.assertPackageIsSelfConsistent(pkg);
            PackageAssertions.assertRegisteredSlideCount(pkg, 2);
        }
        ThirdPartyReadBack.assertReadsAs(good, 2, 1, "One");
    }