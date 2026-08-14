[Fact]
    public void TestAdjustmentProperties()
    {
        // Adjustment values expose name, raw_value, angle_value.
        using var pres = new Presentation();
        var conn = pres.Slides[0].Shapes!.AddConnector(ShapeType.BentConnector3, 50, 50, 300, 200);
        var adjustments = conn.Adjustments;
        if (adjustments is not null && adjustments.Count > 0)
        {
            var adj = adjustments[0];
            adj.Name.Should().NotBeNull();
            adj.RawValue.Should().BeOfType(typeof(int));
            adj.AngleValue.Should().BeOfType(typeof(float));
        }
    }