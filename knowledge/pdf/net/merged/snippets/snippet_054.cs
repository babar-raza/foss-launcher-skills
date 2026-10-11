[Fact]
    public void Page_Number_MatchesIndex()
    {
        var data = PdfBuilder.BuildMultiPage(3);
        using var doc = Document.Open(data);

        for (var i = 1; i <= doc.PageCount; i++)
        {
            Assert.Equal(i, doc.Pages[i].Number);
        }
    }