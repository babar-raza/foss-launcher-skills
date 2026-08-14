describe('testMeshTriangulate', () => {
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
    });

    it('testQuadMesh', () => {
        const quadMesh = new Mesh("quad");
        quadMesh.controlPoints = [
            new Vector4(0, 0, 0, 1),
            new Vector4(1, 0, 0, 1),
            new Vector4(0, 1, 0, 1),
            new Vector4(1, 1, 0, 1)
        ];
        quadMesh.createPolygon(0, 1, 3, 2);

        expect(quadMesh.polygonCount).toBe(1);

        const triangulated = quadMesh.triangulate();
        expect(triangulated.polygonCount).toBe(2);
    });

    it('testPentagonMesh', () => {
        const pentMesh = new Mesh("pentagon");
        pentMesh.controlPoints = [
            new Vector4(0, 0, 0, 1),
            new Vector4(1, 0, 0, 1),
            new Vector4(1.5, 0.5, 0, 1),
            new Vector4(1, 1, 0, 1),
            new Vector4(0, 1, 0, 1)
        ];
        pentMesh.createPolygon([0, 1, 2, 3, 4]);

        expect(pentMesh.polygonCount).toBe(1);

        const triangulated = pentMesh.triangulate();
        expect(triangulated.polygonCount).toBe(3);
    });
})