[Fact]
    public void Sphere_ToMesh_ShouldCreateMesh()
    {
        var sphere = new Sphere(10, 32, 16);
        var mesh = sphere.ToMesh();
        
        Assert.NotNull(mesh);
        Assert.True(mesh.ControlPoints.Count > 0);
        
        SaveMeshToObj(mesh, "Sphere.obj");
    }