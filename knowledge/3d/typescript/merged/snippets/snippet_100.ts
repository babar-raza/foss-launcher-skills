it('testAsciiStlImport', () => {
        const scene = new Scene();
        const content = `solid TestCube
  facet normal 0.0 0.0 -1.0
    outer loop
      vertex 0.0 0.0 0.0
      vertex 1.0 0.0 0.0
      vertex 1.0 1.0 0.0
    endloop
  endfacet
  facet normal 0.0 0.0 -1.0
    outer loop
      vertex 0.0 0.0 0.0
      vertex 1.0 1.0 0.0
      vertex 0.0 1.0 0.0
    endloop
  endfacet
endsolid TestCube
`;
        const stream = new TextEncoder().encode(content);
        const options = new StlLoadOptions();

        scene.openFromBuffer(stream, options);

        expect(scene.rootNode).toBeDefined();
        expect(scene.rootNode.childNodes.length).toBe(1);

        const node = scene.rootNode.childNodes[0];
        expect(node.entity).toBeDefined();

        const mesh = node.entity as Mesh;
        expect(mesh.controlPoints.length).toBe(6);
        expect(mesh.polygonCount).toBe(2);
    })