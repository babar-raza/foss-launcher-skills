test('test_disable_materials', () => {
        const objContent = `# Test disable materials
o TestMesh
usemtl MyMaterial
v 0.0 0.0 0.0
v 1.0 0.0 0.0
f 1 2 3
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        options.enableMaterials = false;
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        if (scene.rootNode.childNodes.length > 0) {
            const node = scene.rootNode.childNodes[0];
            expect(node.material).toBeNull();
        } else {
            fail("No child nodes created");
        }
    })