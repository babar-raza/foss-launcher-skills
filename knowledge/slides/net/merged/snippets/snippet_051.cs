[Fact]
    public void TestMultipleDashStyles()
    {
        // Various dash styles can be set in-memory.
        LineDashStyle[] styles =
        [
            LineDashStyle.Solid,
            LineDashStyle.Dash,
            LineDashStyle.Dot,
            LineDashStyle.DashDot,
        ];

        using var pres = new Presentation();
        var slide = pres.Slides[0];
        foreach (var style in styles)
        {
            var shape = slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 50);
            shape.LineFormat.DashStyle = style;
            shape.LineFormat.DashStyle.Should().Be(style);
        }
    }