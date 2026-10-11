[Fact]
    public void Pyramid_ToMesh_ShouldCreateMesh()
    {
        var pyramid = new Pyramid(10, 10, 20);
        var mesh = pyramid.ToMesh();
        
        Assert.NotNull(mesh);
        Assert.True(mesh.ControlPoints.Count >= 4);
        
        SaveMeshToObj(mesh, "Pyramid.obj");
    }