[Fact]
    public void APowerPointDeckSurvivesTheChecksEveryProducedPackageFaces()
    {
        var path = _workspace.PathFor("roundtrip-checked.pptx");

        using (var presentation = new Presentation(TestFixtures.PowerPointDeck))
        {
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);
        PackageAssert.EveryPartResolvesAContentType(package);
        PackageAssert.EveryPartHasItsRequiredContentType(package);
        PackageAssert.NoOverrideNamesAMissingPart(package);
        PackageAssert.EveryInternalRelationshipTargetExists(package);
        PackageAssert.AllRelationshipReferencesResolve(package);
        SchemaValidation.HasNoSchemaErrors(path);
    }