[Fact]
    public void TestMultipleShapeTypes()
    {
        // Various ShapeType values are preserved.
        ShapeType[] types = [ShapeType.Rectangle, ShapeType.Ellipse, ShapeType.Triangle];
        using var pres = new Presentation();
        var slide = BlankSlide(pres);
        foreach (var st in types)
        {
            var s = slide.Shapes!.AddAutoShape(st, 10, 10, 100, 100);
            s.ShapeType.Should().Be(st);
        }
        slide.Shapes!.Count.Should().Be(3);
    }