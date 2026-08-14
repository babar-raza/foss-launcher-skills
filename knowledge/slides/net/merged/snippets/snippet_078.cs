[Fact]
    public void TestShapeFrameProperties()
    {
        // x, y, width, height, rotation persist after save/reload.
        using var pres = new Presentation();
        var slide = BlankSlide(pres);
        var shape = slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 200, 200, 300, 250);
        shape.Rotation = 45;

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var s2 = pres2.Slides[0].Shapes![0];
        s2.X.Should().Be(200);
        s2.Y.Should().Be(200);
        s2.Width.Should().Be(300);
        s2.Height.Should().Be(250);
        s2.Rotation.Should().Be(45);
    }