[Fact]
    public void TestInsertAutoShape()
    {
        // insert_auto_shape places a shape at the requested index.
        using var pres = new Presentation();
        var slide = BlankSlide(pres);
        slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);
        slide.Shapes!.AddAutoShape(ShapeType.Ellipse, 300, 50, 150, 150);
        slide.Shapes!.InsertAutoShape(1, ShapeType.Triangle, 150, 200, 100, 100);
        slide.Shapes!.Count.Should().Be(3);
    }