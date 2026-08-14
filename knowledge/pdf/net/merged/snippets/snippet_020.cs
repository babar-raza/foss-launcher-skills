[Fact]
    public void CreateNamed_AllStandardNames()
    {
        foreach (var name in new[] { "NextPage", "PrevPage", "FirstPage", "LastPage" })
        {
            var action = PdfAction.CreateNamed(name);
            Assert.Equal(ActionType.Named, action.Type);
        }
    }