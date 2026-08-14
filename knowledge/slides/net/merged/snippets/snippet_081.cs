[Fact]
    public void TestShapePersistsAfterReload()
    {
        // Shapes survive a save/reload cycle.
        using var pres = new Presentation();
        var slide = BlankSlide(pres);
        slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        pres2.Slides[0].Shapes!.Count.Should().BeGreaterThanOrEqualTo(1);
        ((IGeometryShape)pres2.Slides[0].Shapes![0]).ShapeType.Should().Be(ShapeType.Rectangle);
    }