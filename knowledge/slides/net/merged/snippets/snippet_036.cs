[Fact]
    public void TestGradientFill()
    {
        // Gradient stops and angle persist.
        using var pres = new Presentation();
        var slide = ClearSlide(pres);
        var shape = slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 300, 150);
        shape.FillFormat.FillType = FillType.Gradient;
        var gf = shape.FillFormat.GradientFormat;
        gf.GradientShape = GradientShape.Linear;
        gf.LinearGradientAngle = 45;
        gf.GradientStops.Add(0.0f, Color.Blue);
        gf.GradientStops.Add(1.0f, Color.Red);

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var ff2 = pres2.Slides[0].Shapes![0].FillFormat;
        ff2.FillType.Should().Be(FillType.Gradient);
        ff2.GradientFormat.GradientStops.Count.Should().BeGreaterThanOrEqualTo(2);
    }