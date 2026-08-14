[Fact]
    public void TestAddEmptySlide()
    {
        // add_empty_slide increases slide count.
        using var pres = new Presentation();
        var layout = pres.LayoutSlides[0];
        pres.Slides.AddEmptySlide(layout);
        pres.Slides.Count.Should().Be(2);
    }