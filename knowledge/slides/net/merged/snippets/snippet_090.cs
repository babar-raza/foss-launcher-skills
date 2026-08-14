[Fact]
    public void TestSlideLayoutAccess()
    {
        // Each slide exposes its layout_slide.
        using var pres = new Presentation();
        pres.Slides[0].LayoutSlide.Should().NotBeNull();
    }