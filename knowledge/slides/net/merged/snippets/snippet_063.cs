[Fact]
    public void TestSaveToStream()
    {
        // Saving to a MemoryStream produces a non-empty buffer.
        using var pres = new Presentation();
        using var buf = new MemoryStream();
        pres.Save(buf, SaveFormat.Pptx);
        buf.Position.Should().BeGreaterThan(0);
    }