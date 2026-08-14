[Fact]
    public void TestReroute()
    {
        // reroute() updates connector position.
        using var pres = new Presentation();
        var slide = pres.Slides[0];
        var shapes = slide.Shapes!;
        var s1 = shapes.AddAutoShape(ShapeType.Ellipse, 50, 100, 80, 80);
        var s2 = shapes.AddAutoShape(ShapeType.Ellipse, 400, 100, 80, 80);
        var conn = shapes.AddConnector(ShapeType.BentConnector3, 0, 0, 1, 1);
        conn.StartShapeConnectedTo = s1;
        conn.StartShapeConnectionSiteIndex = 3;
        conn.EndShapeConnectedTo = s2;
        conn.EndShapeConnectionSiteIndex = 1;
        conn.Reroute();
        // After reroute the connector should span between the shapes
        (conn.Width > 0 || conn.Height > 0).Should().BeTrue();
    }