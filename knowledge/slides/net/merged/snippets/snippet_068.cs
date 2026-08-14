[Fact]
    public void TestSlideCountAfterAdd()
    {
        // Adding a slide increases slide count to 2.
        using var pres = new Presentation();
        var layout = pres.LayoutSlides[0];
        pres.Slides.AddEmptySlide(layout);
        pres.Slides.Count.Should().Be(2);
    }