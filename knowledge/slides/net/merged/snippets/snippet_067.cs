[Fact]
    public void TestDisposeIsIdempotent()
    {
        // Calling Dispose() twice must not raise.
        using var pres = new Presentation();
        pres.Dispose();
        pres.Dispose(); // second call should be harmless
    }