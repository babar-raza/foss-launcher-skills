[Fact]
    public void AnEnabledFillOverlayCarriesItsBlendModeAndAFill()
    {
        var path = WriteShapeWithEffect("FillOverlay", "effect-fillOverlay.pptx");

        using var package = PptxPackage.Open(path);
        var element = PackageAssert.SingleElement(package, "ppt/slides/slide1.xml", "//a:effectLst/a:fillOverlay");

        Assert.True(element.Attribute("blend") is not null,
            $"<a:fillOverlay> was written as '{element}'. 'blend' is a required attribute of CT_FillOverlayEffect.");

        var fill = element.Elements().FirstOrDefault(child => FillElements.Contains(child.Name.LocalName));
        Assert.True(fill is not null,
            $"<a:fillOverlay> was written as '{element}' — it carries no fill child. " +
            $"CT_FillOverlayEffect requires exactly one of: {string.Join(", ", FillElements)}.");
    }