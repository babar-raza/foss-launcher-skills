[Fact]
    public void CreateGoTo_FitTypes_AllSupported()
    {
        foreach (var fitType in new[] { "Fit", "FitH", "FitV", "XYZ" })
        {
            var action = PdfAction.CreateGoTo(0, fitType);
            Assert.Equal(ActionType.GoTo, action.Type);
        }
    }