private void SaveMeshToObj(Mesh mesh, string filename)
    {
        var scene = new Scene();
        var node = new Node();
        node.Entity = mesh;
        scene.RootNode.ChildNodes.Add(node);
        
        var path = Path.Combine(TestOutputDir, filename);
        scene.Save(path, new ObjSaveOptions());
    }