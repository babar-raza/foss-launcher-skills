[Test]
    public void Save_BasicRgb_RenamesLayer()
    {
        AssertRenameSave("basic-rgb.psd", layerIndex: 1, newName: "Renamed Rectangle");
    }