[Fact]
    public void TestFirstSlideNumber()
    {
        // first_slide_number persists across save/reload.
        using var pres = new Presentation();
        pres.FirstSlideNumber = 5;
        pres.FirstSlideNumber.Should().Be(5);

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        pres2.FirstSlideNumber.Should().Be(5);
    }