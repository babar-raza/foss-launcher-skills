[Fact]
    public void TestRemoveSlideByRef()
    {
        // Removing a slide by reference decreases count.
        using var pres = new Presentation();
        var layout = pres.LayoutSlides[0];
        pres.Slides.AddEmptySlide(layout);
        pres.Slides.Count.Should().Be(2);
        pres.Slides.Remove(pres.Slides[1]);
        pres.Slides.Count.Should().Be(1);
    }