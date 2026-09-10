[Fact]
    public void AnEnabledPresetShadowCarriesItsPresetAttribute()
    {
        var path = WriteShapeWithEffect("PresetShadow", "effect-prstShdw-prst.pptx");

        using var package = PptxPackage.Open(path);
        var element = PackageAssert.SingleElement(package, "ppt/slides/slide1.xml", "//a:effectLst/a:prstShdw");

        Assert.True(element.Attribute("prst") is not null,
            $"<a:prstShdw> was written as '{element}'. 'prst' is a required attribute of CT_PresetShadowEffect.");
    }