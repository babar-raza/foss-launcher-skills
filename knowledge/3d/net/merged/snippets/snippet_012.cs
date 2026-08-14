[Fact]
        public void Cylinder_ToMesh_ShouldCreateValidMesh()
        {
            var cylinder = new Cylinder(1, 1, 2);
            var mesh = cylinder.ToMesh();

            Assert.NotNull(mesh);
            Assert.True(mesh.ControlPoints.Count > 0);
            Assert.True(mesh.PolygonCount > 0);
            Assert.True(mesh.PolygonCount >= 3, "Cylinder should have at least 3 polygons");
        }