[Fact]
    public void TestRemoveShape()
    {
        // Removing a shape by reference decreases count.
        using var pres = new Presentation();
        var slide = BlankSlide(pres);
        var s = slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);
        slide.Shapes!.AddAutoShape(ShapeType.Ellipse, 300, 50, 150, 150);
        slide.Shapes!.Count.Should().Be(2);
        slide.Shapes!.Remove(s);
        slide.Shapes!.Count.Should().Be(1);
    }