describe('testEarClipping', () => {
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
    });

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
    });
})