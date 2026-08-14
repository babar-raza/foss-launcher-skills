[Fact]
    public void AddMultipleAnnotationTypes()
    {
        var input = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(input);
        var page = doc.Pages[1];

        page.Annotations.AddTextAnnotation(new Rectangle(10, 10, 30, 30), "Note");
        page.Annotations.AddHighlightAnnotation(new Rectangle(72, 700, 200, 720));
        page.Annotations.AddInkAnnotation(new Rectangle(100, 500, 200, 550),
            new[] { new double[] { 100, 500, 150, 550 } });

        var saved = doc.ToArray();
        using var doc2 = Document.Open(saved);
        Assert.Equal(3, doc2.Pages[1].Annotations.Count);
    }