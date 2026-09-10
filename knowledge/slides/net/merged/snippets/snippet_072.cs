[Fact]
    public void SavingASubsetOfSlidesWritesOnlyTheSlidesThatWereAskedFor()
    {
        var path = _workspace.PathFor("subset.pptx");

        using (var presentation = new Presentation())
        {
            presentation.Slides.AddEmptySlide(presentation.LayoutSlides[0]);
            presentation.Slides.AddEmptySlide(presentation.LayoutSlides[0]);
            presentation.Save(path, [0], SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);
        var slideIds = PackageAssert.Select(package, "ppt/presentation.xml", "//p:sldIdLst/p:sldId");

        Assert.True(slideIds.Count == 1,
            $"One slide was requested and the saved package registers {slideIds.Count}:{Environment.NewLine}" +
            string.Join(Environment.NewLine, slideIds));
    }