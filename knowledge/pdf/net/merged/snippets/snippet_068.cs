[Fact]
    public void InlineImage_Parsed()
    {
        var parser = CreateParser();
        PdfDictionary? capturedDict = null;
        byte[]? capturedData = null;

        parser.OnInlineImage += (dict, data) =>
        {
            capturedDict = dict;
            capturedData = data;
        };

        // Build a simple inline image: 2x2 grayscale
        var pixels = new byte[] { 0, 64, 128, 255 };
        var sb = new StringBuilder();
        sb.Append("BI\n/W 2 /H 2 /BPC 8 /CS /G\nID ");
        var header = Encoding.ASCII.GetBytes(sb.ToString());
        var footer = Encoding.ASCII.GetBytes(" EI");

        var stream = new byte[header.Length + pixels.Length + footer.Length];
        Array.Copy(header, 0, stream, 0, header.Length);
        Array.Copy(pixels, 0, stream, header.Length, pixels.Length);
        Array.Copy(footer, 0, stream, header.Length + pixels.Length, footer.Length);

        parser.Parse(stream);

        Assert.NotNull(capturedDict);
        Assert.Equal(2, (int)capturedDict!.GetInt("Width"));
        Assert.Equal(2, (int)capturedDict!.GetInt("Height"));
        Assert.Equal(8, (int)capturedDict!.GetInt("BitsPerComponent"));
        Assert.Equal("DeviceGray", capturedDict!.GetName("ColorSpace"));
        Assert.NotNull(capturedData);
        Assert.Equal(pixels, capturedData);
    }