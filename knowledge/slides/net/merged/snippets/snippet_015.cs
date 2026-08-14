[Fact]
    public void TestBentConnectorAdjustments()
    {
        // Adjustment values persist after save/reload.
        using var pres = new Presentation();
        var shapes = pres.Slides[0].Shapes!;
        shapes.Clear();
        var conn = shapes.AddConnector(ShapeType.BentConnector3, 50, 50, 300, 200);
        var adjustments = conn.Adjustments;
        if (adjustments is not null && adjustments.Count > 0)
        {
            adjustments[0].RawValue = 30000;
        }

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        // Find the connector shape
        Connector? conn2 = null;
        foreach (var sh in pres2.Slides[0].Shapes!)
        {
            if (sh is Connector c)
            {
                conn2 = c;
                break;
            }
        }
        conn2.Should().NotBeNull("Connector not found after reload");
        var adj2 = conn2!.Adjustments;
        if (adj2 is not null && adj2.Count > 0)
        {
            adj2[0].RawValue.Should().Be(30000);
        }
    }