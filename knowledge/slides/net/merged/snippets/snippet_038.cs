[Fact]
    public void TestNoFill()
    {
        // NO_FILL type persists.
        using var pres = new Presentation();
        var slide = ClearSlide(pres);
        var shape = slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);
        shape.FillFormat.FillType = FillType.NoFill;

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        pres2.Slides[0].Shapes![0].FillFormat.FillType.Should().Be(FillType.NoFill);
    }