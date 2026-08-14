[Fact]
    public void TestSlideHidden()
    {
        // Setting hidden persists across save/reload.
        using var pres = new Presentation();
        pres.Slides[0].Hidden = true;
        pres.Slides[0].Hidden.Should().BeTrue();

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        pres2.Slides[0].Hidden.Should().BeTrue();
    }