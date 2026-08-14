[Fact]
    public void TestAddAutoShape()
    {
        // add_auto_shape adds a rectangle with correct type.
        using var pres = new Presentation();
        var slide = BlankSlide(pres);
        var shape = slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);
        slide.Shapes!.Count.Should().Be(1);
        shape.ShapeType.Should().Be(ShapeType.Rectangle);
    }