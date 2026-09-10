[Fact]
    public void TestAddStraightConnectorPersists()
    {
        // Straight connector survives save/reload.
        using var pres = new Presentation();
        pres.Slides[0].Shapes!.AddConnector(ShapeType.StraightConnector1, 100, 100, 300, 200);

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        pres2.Slides[0].Shapes!.Count.Should().BeGreaterThanOrEqualTo(1);
    }