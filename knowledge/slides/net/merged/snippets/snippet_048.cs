[Fact]
    public void ALineWidthInPointsIsWrittenInEnglishMetricUnits()
    {
        var path = _workspace.PathFor("line-width.pptx");

        using (var presentation = new Presentation())
        {
            var shape = presentation.Slides[0].Shapes!.AddAutoShape(ShapeType.Rectangle, 10, 10, 100, 100);
            shape.LineFormat.Width = 2.5f;
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);

        // 12,700 EMU to the point.
        PackageAssert.ElementWithAttributes(package, "ppt/slides/slide1.xml", "//p:spPr/a:ln", ("w", "31750"));
    }