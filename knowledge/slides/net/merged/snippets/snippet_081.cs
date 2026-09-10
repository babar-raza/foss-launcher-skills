[Fact]
    public void AnAddedParagraphIsWrittenWithItsPortions()
    {
        var path = _workspace.PathFor("paragraph-add.pptx");

        using (var presentation = new Presentation())
        {
            var shape = presentation.Slides[0].Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 300, 100);
            var textFrame = shape.TextFrame!;
            textFrame.Text = "First paragraph";

            var second = new Paragraph();
            second.Portions.Add(new Portion("Second-A "));
            second.Portions.Add(new Portion("Second-B"));
            textFrame.Paragraphs.Add(second);

            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);

        AssertParagraphTexts(package, ["First paragraph", "Second-A Second-B"]);

        var portions = PackageAssert.Select(package, "ppt/slides/slide1.xml", "//p:txBody/a:p[2]/a:r/a:t");
        Assert.True(portions.Count == 2,
            $"The added paragraph carries {portions.Count} portion(s), expected the two it was given." +
            $"{Environment.NewLine}{PackageAssert.Describe(package, "ppt/slides/slide1.xml")}");
        Assert.Equal("Second-A ", portions[0].Value);
        Assert.Equal("Second-B", portions[1].Value);
    }