[Fact]
    public void TestCloneSlide()
    {
        // add_clone duplicates a slide with its shapes.
        using var pres = new Presentation();
        var slide = pres.Slides[0];
        slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);
        pres.Slides.AddClone(slide);
        pres.Slides.Count.Should().Be(2);
        pres.Slides[1].Shapes!.Count.Should().BeGreaterThanOrEqualTo(1);
    }