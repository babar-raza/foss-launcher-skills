[Fact]
    public void AnAddedParagraphCarryingOnlyTextIsWrittenAsARun()
    {
        var path = _workspace.PathFor("paragraph-add-text.pptx");

        using (var presentation = new Presentation())
        {
            var shape = presentation.Slides[0].Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 300, 100);
            var textFrame = shape.TextFrame!;
            textFrame.Text = "First paragraph";
            textFrame.Paragraphs.Add(new Paragraph { Text = "Second paragraph" });

            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);

        AssertParagraphTexts(package, ["First paragraph", "Second paragraph"]);
    }