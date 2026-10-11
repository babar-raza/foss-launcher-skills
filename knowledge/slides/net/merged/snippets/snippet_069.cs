[Fact]
    public void AnAddedSectionIsWrittenToThePresentationPart()
    {
        var path = _workspace.PathFor("sections.pptx");

        using (var presentation = new Presentation())
        {
            presentation.Slides.AddEmptySlide(presentation.LayoutSlides[0]);
            presentation.Sections.AddSection("Intro", presentation.Slides[0]);
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);

        var sections = PackageAssert.Select(package, "ppt/presentation.xml", "//p14:sectionLst/p14:section");

        Assert.True(sections.Count == 1,
            $"One section was added and the package declares {sections.Count}." +
            $"{Environment.NewLine}{PackageAssert.Describe(package, "ppt/presentation.xml")}");

        Assert.Equal("Intro", (string?)sections[0].Attribute("name"));
    }