[Fact]
    public void AClonedSlideIsDeclaredAsASlide()
    {
        var path = _workspace.PathFor("cloned-slide.pptx");

        using (var presentation = new Presentation())
        {
            presentation.Slides.AddClone(presentation.Slides[0]);
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);
        PackageAssert.EveryPartHasItsRequiredContentType(package);
    }