[Fact]
    public void TestConnectShapes()
    {
        // Start/end connections persist.
        using var pres = new Presentation();
        var slide = pres.Slides[0];
        var shapes = slide.Shapes!;
        shapes.Clear();
        var s1 = shapes.AddAutoShape(ShapeType.Rectangle, 50, 50, 100, 60);
        var s2 = shapes.AddAutoShape(ShapeType.Rectangle, 350, 200, 100, 60);
        var conn = shapes.AddConnector(ShapeType.BentConnector3, 0, 0, 1, 1);

        conn.StartShapeConnectedTo = s1;
        conn.StartShapeConnectionSiteIndex = 3;
        conn.EndShapeConnectedTo = s2;
        conn.EndShapeConnectionSiteIndex = 1;

        conn.StartShapeConnectedTo.Should().NotBeNull();
        conn.EndShapeConnectedTo.Should().NotBeNull();

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        Connector? conn2 = null;
        foreach (var sh in pres2.Slides[0].Shapes!)
        {
            if (sh is Connector c && c.ShapeType == ShapeType.BentConnector3)
            {
                conn2 = c;
                break;
            }
        }
        conn2.Should().NotBeNull();
        conn2!.StartShapeConnectionSiteIndex.Should().Be(3);
        conn2.EndShapeConnectionSiteIndex.Should().Be(1);
    }