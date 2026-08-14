[Fact]
    public void CreateGoTo_ProducesValidGoToAction()
    {
        var action = PdfAction.CreateGoTo(2, "Fit");

        Assert.Equal(ActionType.GoTo, action.Type);
    }