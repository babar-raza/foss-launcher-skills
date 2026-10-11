[Fact]
    public void ExtendedPropertiesProduceASchemaValidPackage()
    {
        var path = _workspace.PathFor("app-properties-valid.pptx");

        using (var presentation = new Presentation())
        {
            // Deliberately set in an order the schema does not declare them in.
            presentation.DocumentProperties.HyperlinkBase = "https://example.com/";
            presentation.DocumentProperties.PresentationFormat = "On-screen Show (4:3)";
            presentation.DocumentProperties.Company = "Example";
            presentation.DocumentProperties.ApplicationTemplate = "Blank";
            presentation.Save(path, SaveFormat.Pptx);
        }

        SchemaValidation.HasNoSchemaErrors(path);
    }