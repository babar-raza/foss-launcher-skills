[Fact]
    public void Box_ToMesh_ShouldCreateMesh()
    {
        var box = new Box(10, 20, 30);
        var mesh = box.ToMesh();
        
        Assert.NotNull(mesh);
        Assert.Equal(8, mesh.ControlPoints.Count);
        
        SaveMeshToObj(mesh, "Box.obj");
    }