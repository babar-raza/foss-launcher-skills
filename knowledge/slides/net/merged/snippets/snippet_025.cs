private string WriteShapeWithEffect(string effect, string fileName)
    {
        var path = _workspace.PathFor(fileName);

        using var presentation = new Presentation();
        var shape = presentation.Slides[0].Shapes!.AddAutoShape(ShapeType.Rectangle, 10, 10, 100, 100);
        Enable(shape.EffectFormat!, effect);
        presentation.Save(path, SaveFormat.Pptx);

        return path;
    }