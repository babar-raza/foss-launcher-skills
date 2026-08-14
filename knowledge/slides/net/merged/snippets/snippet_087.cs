[Fact]
    public void TestRemoveSlideAt()
    {
        // remove_at removes by index.
        using var pres = new Presentation();
        var layout = pres.LayoutSlides[0];
        pres.Slides.AddEmptySlide(layout);
        pres.Slides.RemoveAt(1);
        pres.Slides.Count.Should().Be(1);
    }