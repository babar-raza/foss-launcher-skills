[Fact]
    public void TestIterateSlides()
    {
        // Slides are iterable.
        using var pres = new Presentation();
        var layout = pres.LayoutSlides[0];
        pres.Slides.AddEmptySlide(layout);
        var slides = pres.Slides.ToList();
        slides.Count.Should().Be(2);
    }