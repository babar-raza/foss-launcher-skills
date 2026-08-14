[Fact]
    public void TestRemoveAt()
    {
        // remove_at removes by index.
        using var pres = new Presentation();
        var slide = BlankSlide(pres);
        slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);
        slide.Shapes!.AddAutoShape(ShapeType.Ellipse, 300, 50, 150, 150);
        slide.Shapes!.RemoveAt(0);
        slide.Shapes!.Count.Should().Be(1);
    }