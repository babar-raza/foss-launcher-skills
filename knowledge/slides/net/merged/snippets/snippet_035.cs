[Fact]
    public void TestSolidFill()
    {
        // Solid fill colour persists after save/reload.
        using var pres = new Presentation();
        var slide = ClearSlide(pres);
        var shape = slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);
        shape.FillFormat.FillType = FillType.Solid;
        shape.FillFormat.SolidFillColor.Color = Color.FromArgb(255, 0, 128, 255);

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var ff = pres2.Slides[0].Shapes![0].FillFormat;
        ff.FillType.Should().Be(FillType.Solid);
        var c = ff.SolidFillColor.Color;
        c!.R.Should().Be(0);
        c.G.Should().Be(128);
        c.B.Should().Be(255);
    }