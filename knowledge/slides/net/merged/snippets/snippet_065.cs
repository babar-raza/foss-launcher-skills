[Theory]
    [InlineData(SaveFormat.Pptm, "pptm", "application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml")]
    [InlineData(SaveFormat.Ppsm, "ppsm", "application/vnd.ms-powerpoint.slideshow.macroEnabled.main+xml")]
    [InlineData(SaveFormat.Potm, "potm", "application/vnd.ms-powerpoint.template.macroEnabled.main+xml")]
    public void MacroEnabledFormatsAreNotWrittenAsAPlainPresentation(SaveFormat format, string extension, string macroContentType)
    {
        var path = _workspace.PathFor($"deck.{extension}");

        using var presentation = new Presentation();
        var thrown = Record.Exception(() => presentation.Save(path, format));
        if (thrown is NotSupportedException)
            return; // Refusing to write a macro-enabled package it cannot honour is an acceptable answer.

        Assert.Null(thrown);

        using var package = PptxPackage.Open(path);
        var actual = package.ContentTypeOf("ppt/presentation.xml");

        Assert.True(macroContentType == actual,
            $"Saved as .{extension} without raising, and /ppt/presentation.xml is declared " +
            $"'{actual ?? "nothing"}'.{Environment.NewLine}" +
            $"A macro-enabled package must either raise NotSupportedException or declare '{macroContentType}'.");
    }