[Fact]
    public void TestCreateEmpty()
    {
        // A brand-new presentation has exactly 1 slide.
        using var pres = new Presentation();
        pres.Slides.Count.Should().Be(1);
    }