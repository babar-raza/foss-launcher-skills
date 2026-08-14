[Fact]
    public void TestSaveAndReload()
    {
        // Round-trip: create → save → reload preserves slide count.
        using var pres = new Presentation();
        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        pres2.Slides.Count.Should().Be(1);
    }