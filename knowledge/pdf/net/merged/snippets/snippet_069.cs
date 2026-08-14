[Fact]
    public void InlineImage_AbbreviatedKeys_Expanded()
    {
        var parser = CreateParser();
        PdfDictionary? capturedDict = null;

        parser.OnInlineImage += (dict, _) => capturedDict = dict;

        // Use abbreviated keys: W, H, BPC, CS
        var pixels = new byte[] { 255 };
        var sb = new StringBuilder();
        sb.Append("BI\n/W 1 /H 1 /BPC 8 /CS /RGB\nID ");
        var header = Encoding.ASCII.GetBytes(sb.ToString());
        var footer = Encoding.ASCII.GetBytes(" EI");

        var stream = new byte[header.Length + pixels.Length + footer.Length];
        Array.Copy(header, 0, stream, 0, header.Length);
        Array.Copy(pixels, 0, stream, header.Length, pixels.Length);
        Array.Copy(footer, 0, stream, header.Length + pixels.Length, footer.Length);

        parser.Parse(stream);

        Assert.NotNull(capturedDict);
        Assert.Equal(1, (int)capturedDict!.GetInt("Width"));
        Assert.Equal("DeviceRGB", capturedDict!.GetName("ColorSpace"));
    }