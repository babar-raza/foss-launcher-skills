[Test]
    public void Save_LayeredPsb_RenamesLayer()
    {
        AssertRenameSave("layered.psb", layerIndex: 1, newName: "Renamed Rectangle");
    }