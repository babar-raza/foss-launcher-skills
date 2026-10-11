[Fact]
    public void AddingAShapeToAPowerPointDeckKeepsEveryOtherPart()
    {
        var path = _workspace.PathFor("roundtrip-mutated.pptx");

        using (var presentation = new Presentation(TestFixtures.PowerPointDeck))
        {
            presentation.Slides[0].Shapes!.AddAutoShape(ShapeType.Rectangle, 10, 10, 100, 100);
            presentation.Save(path, SaveFormat.Pptx);
        }

        AssertSamePartSet(TestFixtures.PowerPointDeck, path);

        using var package = PptxPackage.Open(path);

        // The deck's own two shapes, plus the one just added.
        var shapes = PackageAssert.Select(package, "ppt/slides/slide1.xml", "//p:spTree/p:sp");
        Assert.True(shapes.Count == 3,
            $"slide1 carries {shapes.Count} shapes, expected the deck's two plus the added one.");
    }