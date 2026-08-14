[Fact]
    public void TestClearShapes()
    {
        // clear() empties the shape collection.
        using var pres = new Presentation();
        var slide = pres.Slides[0];
        slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);
        slide.Shapes!.Clear();
        slide.Shapes!.Count.Should().Be(0);
    }