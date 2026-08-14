[Fact]
    public void TestOuterShadow()
    {
        // Outer shadow properties persist after save/reload.
        using var pres = new Presentation();
        var slide = pres.Slides[0];
        slide.Shapes!.Clear();
        var shape = slide.Shapes.AddAutoShape(ShapeType.Rectangle, 100, 100, 200, 100);
        var ef = shape.EffectFormat;
        ef.EnableOuterShadowEffect();
        var shadow = ef.OuterShadowEffect!;
        shadow.BlurRadius = 10;
        shadow.Direction = 315;
        shadow.Distance = 8;
        shadow.ShadowColor.Color = Color.FromArgb(128, 0, 0, 0);

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var ef2 = pres2.Slides[0].Shapes![0].EffectFormat;
        var s2 = ef2.OuterShadowEffect;
        s2.Should().NotBeNull("outer_shadow_effect should not be None after reload");
        s2!.BlurRadius.Should().Be(10);
        s2.Direction.Should().Be(315);
        s2.Distance.Should().Be(8);
    }