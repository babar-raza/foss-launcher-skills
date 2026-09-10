[Fact]
    public void AModifiedPackageIsAcceptedByAStrictReader()
    {
        var path = _workspace.PathFor("strict-reader.pptx");

        using (var presentation = new Presentation())
        {
            presentation.Slides.AddEmptySlide(presentation.LayoutSlides[0]);
            presentation.Save(path, SaveFormat.Pptx);
        }

        SchemaValidation.HasNoSchemaErrors(path);
    }