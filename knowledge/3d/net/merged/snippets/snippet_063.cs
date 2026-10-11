[Fact]
    public void Cylinder_ToMesh_ShouldCreateMesh()
    {
        var cylinder = new Cylinder(5, 5, 20);
        var mesh = cylinder.ToMesh();
        
        Assert.NotNull(mesh);
        Assert.True(mesh.ControlPoints.Count > 0);
        
        SaveMeshToObj(mesh, "Cylinder.obj");
    }