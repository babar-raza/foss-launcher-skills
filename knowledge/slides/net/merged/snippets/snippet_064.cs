[Theory]
    [InlineData(SaveFormat.Pptx, "pptx", PresentationContentType)]
    [InlineData(SaveFormat.Potx, "potx", "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml")]
    [InlineData(SaveFormat.Ppsx, "ppsx", "application/vnd.openxmlformats-officedocument.presentationml.slideshow.main+xml")]
    public void TheRequestedFormatDecidesTheMainPartContentType(SaveFormat format, string extension, string expected)
    {
        var path = _workspace.PathFor($"deck.{extension}");

        using (var presentation = new Presentation())
        {
            presentation.Save(path, format);
        }

        using var package = PptxPackage.Open(path);
        var actual = package.ContentTypeOf("ppt/presentation.xml");

        Assert.True(expected == actual,
            $"Saved as .{extension}, but /ppt/presentation.xml is declared " +
            $"'{actual ?? "nothing"}'{Environment.NewLine}expected '{expected}'.");
    }