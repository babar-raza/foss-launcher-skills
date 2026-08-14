[Fact]
    public void TestBlur()
    {
        // Blur effect persists.
        using var pres = new Presentation();
        var slide = pres.Slides[0];
        slide.Shapes!.Clear();
        var shape = slide.Shapes.AddAutoShape(ShapeType.Rectangle, 100, 100, 200, 100);
        var ef = shape.EffectFormat;
        ef.SetBlurEffect(8, true);

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var b2 = pres2.Slides[0].Shapes![0].EffectFormat.BlurEffect;
        b2.Should().NotBeNull("blur_effect should not be None after reload");
        b2!.Radius.Should().Be(8);
    }