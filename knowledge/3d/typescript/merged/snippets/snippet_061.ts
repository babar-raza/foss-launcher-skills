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
    })