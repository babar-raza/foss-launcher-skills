[Fact]
    public void TestAddStraightConnector()
    {
        // Add a straight connector with correct type.
        using var pres = new Presentation();
        var slide = pres.Slides[0];
        var conn = slide.Shapes!.AddConnector(ShapeType.StraightConnector1, 100, 100, 300, 200);
        conn.ShapeType.Should().Be(ShapeType.StraightConnector1);
    }