[Fact]
    public void TestLineDashStyle()
    {
        // Dash style persists.
        using var pres = new Presentation();
        var slide = ClearSlide(pres);
        var shape = slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);
        var lf = shape.LineFormat;
        lf.Width = 3;
        lf.DashStyle = LineDashStyle.Dash;
        lf.FillFormat.FillType = FillType.Solid;
        lf.FillFormat.SolidFillColor.Color = Color.Black;

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var lf2 = pres2.Slides[0].Shapes![0].LineFormat;
        lf2.DashStyle.Should().Be(LineDashStyle.Dash);
    }