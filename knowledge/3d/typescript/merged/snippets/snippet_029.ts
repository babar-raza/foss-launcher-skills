it('testStarShapeHighlyConcave', () => {
        const starMesh = new Mesh('star');
        starMesh.controlPoints = [
            new Vector4(0, 1, 0, 1),
            new Vector4(0.3, 0.3, 0, 1),
            new Vector4(1, 0.3, 0, 1),
            new Vector4(0.4, -0.1, 0, 1),
            new Vector4(0.5, -0.6, 0, 1),
            new Vector4(0.2, -0.2, 0, 1),
            new Vector4(-0.5, -0.6, 0, 1),
            new Vector4(-0.1, -0.1, 0, 1),
            new Vector4(-1, 0.3, 0, 1),
            new Vector4(-0.3, 0.3, 0, 1),
        ];
        starMesh.createPolygon([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);

        expect(starMesh.polygonCount).toBe(1);

        const triangulated = PolygonModifier.triangulate(starMesh);
        
        expect(triangulated.polygonCount).toBe(8);
    })