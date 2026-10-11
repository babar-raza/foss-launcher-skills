[Fact]
    public void SvgDevice_FullOpacity_NoOpacityAttribute()
    {
        // Without ExtGState, no fill-opacity should appear
        var contentBytes = Encoding.ASCII.GetBytes("BT /F1 12 Tf 100 700 Td (Hello) Tj ET");
        var pdf = PdfBuilder.BuildWithTextContent(contentBytes);
        using var doc = Document.Open(pdf);
        var page = doc.Pages[1];

        var device = new Aspose.Pdf.Devices.SvgDevice();
        var svg = device.Process(page);

        Assert.DoesNotContain("fill-opacity", svg);
        Assert.DoesNotContain("mix-blend-mode", svg);
    }