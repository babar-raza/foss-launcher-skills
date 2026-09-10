[Fact]
    public void ACustomPropertyProducesAPartThePackageDeclaresAndCanReach()
    {
        var path = _workspace.PathFor("custom-properties.pptx");

        using (var presentation = new Presentation())
        {
            presentation.DocumentProperties.SetCustomPropertyValue("Reviewer", "QA");
            presentation.Save(path, SaveFormat.Pptx);
        }

        using (var package = PptxPackage.Open(path))
        {
            Assert.True(package.Contains("docProps/custom.xml"),
                $"No custom properties part was written. Parts: {string.Join(", ", package.PartNames)}");

            PackageAssert.EveryPartResolvesAContentType(package);
            PackageAssert.AllRelationshipReferencesResolve(package);

            var declared = package.Relationships(string.Empty)
                .Any(relationship => relationship.Type == Ns.CustomPropertiesRelationshipType);

            Assert.True(declared,
                "The package root declares no custom-properties relationship, so nothing points at " +
                "docProps/custom.xml." +
                $"{Environment.NewLine}{PackageAssert.Describe(package, "_rels/.rels")}");
        }

        SchemaValidation.HasNoSchemaErrors(path);
    }