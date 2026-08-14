[Fact]
    public void TestIterateShapes()
    {
        // Shapes collection is iterable.
        using var pres = new Presentation();
        var slide = BlankSlide(pres);
        slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);
        slide.Shapes!.AddAutoShape(ShapeType.Ellipse, 300, 50, 150, 150);
        var shapes = slide.Shapes!.ToList();
        shapes.Count.Should().Be(2);
    }