[Fact]
    public void AnInsertedParagraphIsWrittenAtTheIndexItWasGiven()
    {
        var path = _workspace.PathFor("paragraph-insert.pptx");

        using (var presentation = new Presentation())
        {
            var shape = presentation.Slides[0].Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 300, 100);
            var textFrame = shape.TextFrame!;
            textFrame.Text = "Second paragraph";
            textFrame.Paragraphs.Insert(0, new Paragraph { Text = "First paragraph" });

            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);

        AssertParagraphTexts(package, ["First paragraph", "Second paragraph"]);
    }