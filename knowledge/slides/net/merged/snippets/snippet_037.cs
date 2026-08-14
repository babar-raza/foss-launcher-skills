[Fact]
    public void TestPatternFill()
    {
        // Pattern style and colours persist.
        using var pres = new Presentation();
        var slide = ClearSlide(pres);
        var shape = slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);
        shape.FillFormat.FillType = FillType.Pattern;
        var pf = shape.FillFormat.PatternFormat;
        pf.PatternStyle = PatternStyle.Percent50;
        pf.ForeColor.Color = Color.DarkBlue;
        pf.BackColor.Color = Color.LightYellow;

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var ff2 = pres2.Slides[0].Shapes![0].FillFormat;
        ff2.FillType.Should().Be(FillType.Pattern);
        ff2.PatternFormat.PatternStyle.Should().Be(PatternStyle.Percent50);
    }