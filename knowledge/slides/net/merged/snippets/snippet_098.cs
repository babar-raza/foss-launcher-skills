[Fact]
    public void TestCreateTable()
    {
        // Create a table and verify row/column counts.
        using var pres = new Presentation();
        var slide = BlankSlide(pres);
        var table = slide.Shapes!.AddTable(50, 50, [100, 150, 200], [40, 40, 40]);
        table.Rows.Count.Should().Be(3);
        table.Columns.Count.Should().Be(3);
    }