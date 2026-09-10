[Fact]
    public void AnEmptyDeckIsAWellFormedPackage()
    {
        var path = _workspace.PathFor("empty.pptx");

        using (var presentation = new Presentation())
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