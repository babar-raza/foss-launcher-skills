[Fact]
    public void CreateNamed_StoresNamedAction()
    {
        var action = PdfAction.CreateNamed("NextPage");

        Assert.Equal(ActionType.Named, action.Type);
    }