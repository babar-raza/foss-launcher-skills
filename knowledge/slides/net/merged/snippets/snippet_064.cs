[Fact]
    public void TestContextManager()
    {
        // Presentation can be used as a context manager (IDisposable / using).
        using var pres = new Presentation();
        pres.Slides.Count.Should().BeGreaterThanOrEqualTo(1);
    }