internal TestWorkspace()
    {
        _root = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "slides-foss-conformance", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_root);
    }