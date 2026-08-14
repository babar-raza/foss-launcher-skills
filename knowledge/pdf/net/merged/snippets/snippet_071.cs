[Fact]
    public void ColorSpace_CS_SetsStrokeColorSpace()
    {
        var parser = CreateParser();
        var content = Encoding.ASCII.GetBytes("/DeviceCMYK CS");
        parser.Parse(content);

        Assert.Equal("DeviceCMYK", parser.State.StrokeColorSpace);
    }