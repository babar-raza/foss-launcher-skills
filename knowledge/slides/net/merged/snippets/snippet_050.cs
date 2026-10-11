[Fact]
    public void MergedTableCellsAreWrittenAsASpanAndAContinuation()
    {
        var path = _workspace.PathFor("merged-cells.pptx");

        using (var presentation = new Presentation())
        {
            var table = presentation.Slides[0].Shapes!.AddTable(50, 50, [100, 100], [30, 30]);
            table.MergeCells(table.Rows[0][0], table.Rows[0][1], false);
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);

        PackageAssert.ElementWithAttributes(package, "ppt/slides/slide1.xml", "//a:tr[1]/a:tc[1]", ("gridSpan", "2"));
        PackageAssert.ElementWithAttributes(package, "ppt/slides/slide1.xml", "//a:tr[1]/a:tc[2]", ("hMerge", "1"));
    }