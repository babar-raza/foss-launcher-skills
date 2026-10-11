[Fact]
    public void Mesh_ToMesh_ShouldReturnSameMesh()
    {
        var mesh = new Mesh();
        mesh.CreatePolygon(new int[] { 0, 1, 2 });
        
        var result = mesh.ToMesh();
        
        Assert.NotNull(result);
        Assert.Equal(mesh, result);
    }