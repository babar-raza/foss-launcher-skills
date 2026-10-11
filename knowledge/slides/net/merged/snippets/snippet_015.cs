[Fact]
    public void ExtendedPropertiesReportTheNumberOfSlidesInTheDeck()
    {
        var path = _workspace.PathFor("app-properties.pptx");

        using (var presentation = new Presentation())
        {
            presentation.Slides.AddEmptySlide(presentation.LayoutSlides[0]);
            presentation.Slides.AddEmptySlide(presentation.LayoutSlides[0]);
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);

        var slideCount = PackageAssert.Select(package, "ppt/presentation.xml", "//p:sldIdLst/p:sldId").Count;
        Assert.Equal(3, slideCount);

        var declared = package.Xml("docProps/app.xml").Root?.Element(Ns.Ep + "Slides")?.Value;

        Assert.True(declared == slideCount.ToString(),
            $"The deck registers {slideCount} slides and docProps/app.xml declares " +
            $"{(declared is null ? "no <Slides> element at all" : $"'{declared}'")}." +
            $"{Environment.NewLine}{PackageAssert.Describe(package, "docProps/app.xml")}");
    }