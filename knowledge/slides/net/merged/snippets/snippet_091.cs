[Fact]
    public void TestSlideName()
    {
        // Slide name persists after save/reload.
        using var pres = new Presentation();
        pres.Slides[0].Name = "MySlide";
        pres.Slides[0].Name.Should().Be("MySlide");

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        pres2.Slides[0].Name.Should().Be("MySlide");
    }