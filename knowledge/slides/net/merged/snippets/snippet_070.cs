[Fact]
    public void ASectionRegistersTheSlidesItContains()
    {
        var path = _workspace.PathFor("sections-slides.pptx");

        using (var presentation = new Presentation())
        {
            presentation.Sections.AddSection("Intro", presentation.Slides[0]);
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);

        var sectionSlideIds = PackageAssert.Select(
            package, "ppt/presentation.xml", "//p14:sectionLst/p14:section/p14:sldIdLst/p14:sldId");

        Assert.True(sectionSlideIds.Count == 1,
            $"The section should list the one slide it starts from; the package lists {sectionSlideIds.Count}." +
            $"{Environment.NewLine}{PackageAssert.Describe(package, "ppt/presentation.xml")}");
    }