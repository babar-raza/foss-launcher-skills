[Fact]
    public void TestIndexOf()
    {
        // index_of returns the correct position.
        using var pres = new Presentation();
        var layout = pres.LayoutSlides[0];
        pres.Slides.AddEmptySlide(layout);
        pres.Slides.IndexOf(pres.Slides[0]).Should().Be(0);
        pres.Slides.IndexOf(pres.Slides[1]).Should().Be(1);
    }