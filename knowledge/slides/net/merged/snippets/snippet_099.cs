[Fact]
    public void TestCellText()
    {
        // Cell text round-trips through save/reload.
        using var pres = new Presentation();
        var slide = BlankSlide(pres);
        var table = slide.Shapes!.AddTable(50, 50, [100, 100], [40, 40]);
        table.Rows[0][0].TextFrame!.Text = "A";
        table.Rows[0][1].TextFrame!.Text = "B";
        table.Rows[1][0].TextFrame!.Text = "C";
        table.Rows[1][1].TextFrame!.Text = "D";

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var t2 = FindTable(pres2.Slides[0]);
        t2.Should().NotBeNull();
        t2!.Rows[0][0].TextFrame!.Text.Should().Be("A");
        t2.Rows[0][1].TextFrame!.Text.Should().Be("B");
        t2.Rows[1][0].TextFrame!.Text.Should().Be("C");
        t2.Rows[1][1].TextFrame!.Text.Should().Be("D");
    }