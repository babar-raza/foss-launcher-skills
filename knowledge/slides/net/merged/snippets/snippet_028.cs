[Fact]
    public void TestGlow()
    {
        // Glow effect persists.
        using var pres = new Presentation();
        var slide = pres.Slides[0];
        slide.Shapes!.Clear();
        var shape = slide.Shapes.AddAutoShape(ShapeType.Ellipse, 100, 100, 200, 200);
        var ef = shape.EffectFormat;
        ef.EnableGlowEffect();
        ef.GlowEffect!.Radius = 15;
        ef.GlowEffect.Color.Color = Color.Gold;

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var g2 = pres2.Slides[0].Shapes![0].EffectFormat.GlowEffect;
        g2.Should().NotBeNull("glow_effect should not be None after reload");
        g2!.Radius.Should().Be(15);
    }