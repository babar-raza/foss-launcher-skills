[Fact]
    public void AnInsertedSlideIsDeclaredAsASlide()
    {
        var path = _workspace.PathFor("inserted-slide.pptx");

        using (var presentation = new Presentation())
        {
            presentation.Slides.InsertEmptySlide(0, presentation.LayoutSlides[0]);
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);
        PackageAssert.EveryPartHasItsRequiredContentType(package);
    }