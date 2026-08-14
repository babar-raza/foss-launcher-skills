[Fact]
    public void TestReorderShapes()
    {
        // reorder() changes the z-order of shapes.
        using var pres = new Presentation();
        var slide = BlankSlide(pres);
        slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);
        var ellipse = slide.Shapes!.AddAutoShape(ShapeType.Ellipse, 300, 50, 150, 150);
        slide.Shapes!.Reorder(0, ellipse);
        ((IGeometryShape)slide.Shapes![0]).ShapeType.Should().Be(ShapeType.Ellipse);
    }