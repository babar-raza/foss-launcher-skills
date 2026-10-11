[Theory]
    [InlineData("OuterShadow", "outerShdw")]
    [InlineData("InnerShadow", "innerShdw")]
    [InlineData("Glow", "glow")]
    [InlineData("PresetShadow", "prstShdw")]
    public void AnEnabledShadowOrGlowCarriesTheColourItsTypeRequires(string effect, string tag)
    {
        var path = WriteShapeWithEffect(effect, $"effect-colour-{effect}.pptx");

        using var package = PptxPackage.Open(path);
        var element = PackageAssert.SingleElement(package, "ppt/slides/slide1.xml", $"//a:effectLst/a:{tag}");

        var colour = element.Elements().FirstOrDefault(child => ColourChoiceElements.Contains(child.Name.LocalName));

        Assert.True(colour is not null,
            $"<a:{tag}> was written as '{element}' — it carries no colour child. " +
            $"ECMA-376 §20.1.8 requires exactly one of: {string.Join(", ", ColourChoiceElements)}.");
    }