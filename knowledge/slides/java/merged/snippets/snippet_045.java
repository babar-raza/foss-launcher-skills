private static void assertNothingRefersToAMissingPart(Path pptx) throws IOException {
        try (PptxPackage pkg = PptxPackage.open(pptx)) {
            PackageAssertions.assertNoContentTypeOverrideNamesAMissingPart(pkg);
            PackageAssertions.assertEveryInternalRelationshipTargetExists(pkg);
            PackageAssertions.assertEveryRelationshipReferenceResolves(pkg);
            assertThat(pkg.entryNames())
                    .as("parts left in %s", pptx)
                    .isNotEmpty();
        }
    }