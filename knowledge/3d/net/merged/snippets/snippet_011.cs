[Fact]
        public void Sphere_ToMesh_ShouldCreateValidMesh()
        {
            var sphere = new Sphere(1);
            var mesh = sphere.ToMesh();

            Assert.NotNull(mesh);
            Assert.True(mesh.ControlPoints.Count > 0);
            Assert.True(mesh.PolygonCount > 0);
            Assert.True(mesh.PolygonCount >= 32, "Sphere should have at least 32 polygons");
        }