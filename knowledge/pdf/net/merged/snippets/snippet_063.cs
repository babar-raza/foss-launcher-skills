[Fact]
    public void MarkedContent_BMC_FiresEvent()
    {
        var parser = CreateParser();
        string? capturedTag = null;
        PdfDictionary? capturedProps = null;

        parser.OnMarkedContentBegin += (tag, props) =>
        {
            capturedTag = tag;
            capturedProps = props;
        };

        var content = Encoding.ASCII.GetBytes("/Span BMC\nEMC");
        parser.Parse(content);

        Assert.Equal("Span", capturedTag);
        Assert.Null(capturedProps);
    }