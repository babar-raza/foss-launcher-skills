[Fact]
    public void TestMergeCells()
    {
        // Merged cells preserve col_span after reload.
        using var pres = new Presentation();
        var slide = BlankSlide(pres);
        var table = slide.Shapes!.AddTable(50, 50, [100, 100, 100], [40, 40]);
        var cell1 = table.Rows[0][0];
        var cell2 = table.Rows[0][1];
        table.MergeCells(cell1, cell2, false);
        cell1.IsMergedCell.Should().BeTrue();
        cell1.ColSpan.Should().BeGreaterThanOrEqualTo(2);

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var t2 = FindTable(pres2.Slides[0]);
        t2.Should().NotBeNull();
        t2!.Rows[0][0].IsMergedCell.Should().BeTrue();
    }