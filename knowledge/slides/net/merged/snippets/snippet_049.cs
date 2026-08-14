[Fact]
    public void TestLineColorAndWidth()
    {
        // Line colour and width persist after save/reload.
        using var pres = new Presentation();
        var slide = ClearSlide(pres);
        var shape = slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);
        var lf = shape.LineFormat;
        lf.Width = 5;
        lf.FillFormat.FillType = FillType.Solid;
        lf.FillFormat.SolidFillColor.Color = Color.DarkRed;

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var lf2 = pres2.Slides[0].Shapes![0].LineFormat;
        lf2.Width.Should().Be(5);
        lf2.FillFormat.FillType.Should().Be(FillType.Solid);
        var c = lf2.FillFormat.SolidFillColor.Color;
        c!.R.Should().Be(Color.DarkRed.R);
    }