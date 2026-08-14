[Fact]
    public void TestEnableDisableEffects()
    {
        // Effects can be enabled then disabled.
        using var pres = new Presentation();
        var shape = pres.Slides[0].Shapes!.AddAutoShape(ShapeType.Rectangle, 100, 100, 200, 100);
        var ef = shape.EffectFormat;
        ef.EnableOuterShadowEffect();
        ef.EnableGlowEffect();
        ef.IsNoEffects.Should().BeFalse();

        ef.DisableOuterShadowEffect();
        ef.DisableGlowEffect();
        ef.IsNoEffects.Should().BeTrue();
    }