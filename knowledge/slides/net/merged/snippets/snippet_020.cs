[Theory]
    [InlineData("Blur")]
    [InlineData("FillOverlay")]
    [InlineData("Glow")]
    [InlineData("InnerShadow")]
    [InlineData("OuterShadow")]
    [InlineData("PresetShadow")]
    [InlineData("Reflection")]
    [InlineData("SoftEdge")]
    public void EnablingAnEffectProducesASchemaValidPackage(string effect)
    {
        var path = WriteShapeWithEffect(effect, $"effect-{effect}.pptx");

        SchemaValidation.HasNoSchemaErrors(path);
    }