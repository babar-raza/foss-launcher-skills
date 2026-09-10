private string WriteDeckWithATable(string fileName)
    {
        var path = _workspace.PathFor(fileName);

        using var presentation = new Presentation();
        presentation.Slides[0].Shapes!.AddTable(50, 50, [100, 100], [30, 30]);
        presentation.Save(path, SaveFormat.Pptx);

        return path;
    }