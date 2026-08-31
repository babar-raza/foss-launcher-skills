it('testConcavePolygonArrowShape', () => {
        const concaveMesh = new Mesh('concave');
        concaveMesh.controlPoints = [
            new Vector4(0, 0, 0, 1),
            new Vector4(2, 0, 0, 1),
            new Vector4(2, 1, 0, 1),
            new Vector4(1, 1, 0, 1),
            new Vector4(1, 2, 0, 1),
            new Vector4(0, 2, 0, 1),
        ];
        concaveMesh.createPolygon([0, 1, 2, 3, 4, 5]);

        expect(concaveMesh.polygonCount).toBe(1);

        const triangulated = PolygonModifier.triangulate(concaveMesh);
        
        expect(triangulated.polygonCount).toBeGreaterThan(0);
    })