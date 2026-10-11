[Fact]
    public void Torus_ToMesh_ShouldCreateMesh()
    {
        var torus = new Torus(10, 3);
        var mesh = torus.ToMesh();
        
        Assert.NotNull(mesh);
        Assert.True(mesh.ControlPoints.Count > 0);
        
        SaveMeshToObj(mesh, "Torus.obj");
    }