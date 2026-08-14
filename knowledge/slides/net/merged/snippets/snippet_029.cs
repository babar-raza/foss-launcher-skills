[Fact]
    public void TestSoftEdge()
    {
        // Soft edge radius persists.
        using var pres = new Presentation();
        var slide = pres.Slides[0];
        slide.Shapes!.Clear();
        var shape = slide.Shapes.AddAutoShape(ShapeType.Rectangle, 100, 100, 200, 100);
        var ef = shape.EffectFormat;
        ef.EnableSoftEdgeEffect();
        ef.SoftEdgeEffect!.Radius = 10;

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var se2 = pres2.Slides[0].Shapes![0].EffectFormat.SoftEdgeEffect;
        se2.Should().NotBeNull("soft_edge_effect should not be None after reload");
        se2!.Radius.Should().Be(10);
    }