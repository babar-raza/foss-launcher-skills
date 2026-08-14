it('testTriangleMeshAlreadyTriangulated', () => {
        const triangleMesh = new Mesh("triangle");
        triangleMesh.controlPoints = [
            new Vector4(0, 0, 0, 1),
            new Vector4(1, 0, 0, 1),
            new Vector4(0, 1, 0, 1)
        ];
        triangleMesh.createPolygon(0, 1, 2);

        expect(triangleMesh.polygonCount).toBe(1);

        const triangulated = triangleMesh.triangulate();
        expect(triangulated.polygonCount).toBe(1);
    })