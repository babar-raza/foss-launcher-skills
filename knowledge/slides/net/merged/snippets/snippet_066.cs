[Fact]
    public void TestLoadExisting()
    {
        // Load a known .pptx from test_data and verify it opens.
        var path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "test_data", "Presentation.pptx");

        using var pres = new Presentation(path);
        pres.Slides.Count.Should().BeGreaterThanOrEqualTo(1);
    }