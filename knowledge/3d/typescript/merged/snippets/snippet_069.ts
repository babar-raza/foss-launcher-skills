describe('testMesh', () => {
    it('testMeshClass', () => {
        const m = new Mesh("test_mesh");

        m.controlPoints.push(new Vector4(0, 0, 0, 1));
        m.controlPoints.push(new Vector4(1, 0, 0, 1));
        m.controlPoints.push(new Vector4(0, 1, 0, 1));

        expect(m.controlPoints.length).toBe(3);

        m.createPolygon(0, 1, 2);
        expect(m.polygonCount).toBe(1);

        m.createPolygon(0, 1, 2, 3);
        expect(m.polygonCount).toBe(2);

        m.createPolygon([4, 5, 6, 7, 8]);
        expect(m.polygonCount).toBe(3);

        m.createElement(VertexElementType.NORMAL, MappingMode.CONTROL_POINT, null);
        expect(m.vertexElements.length).toBe(1);

        const uvElem = m.createElementUV(TextureMapping.DIFFUSE);
        expect(uvElem.textureMapping).toBe(TextureMapping.DIFFUSE);
    });
})