[Fact]
    public void AnAddedSlideIsDeclaredAsASlide()
    {
        var path = _workspace.PathFor("added-slide.pptx");

        using (var presentation = new Presentation())
        {
            presentation.Slides.AddEmptySlide(presentation.LayoutSlides[0]);
            presentation.Slides.AddEmptySlide(presentation.LayoutSlides[0]);
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);
        PackageAssert.EveryPartHasItsRequiredContentType(package);
    }