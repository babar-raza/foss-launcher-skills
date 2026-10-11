[Fact]
    public void Dish_ToMesh_ShouldCreateMesh()
    {
        var dish = new Dish(10, 5);
        var mesh = dish.ToMesh();
        
        Assert.NotNull(mesh);
        Assert.True(mesh.ControlPoints.Count > 0);
        
        SaveMeshToObj(mesh, "Dish.obj");
    }