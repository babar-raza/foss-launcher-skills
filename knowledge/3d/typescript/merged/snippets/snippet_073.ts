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
    })