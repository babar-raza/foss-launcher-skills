[Fact]
    public void ADeckWithSeveralParagraphsIsSchemaValid()
    {
        var path = _workspace.PathFor("paragraph-valid.pptx");

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

        SchemaValidation.HasNoSchemaErrors(path);
    }