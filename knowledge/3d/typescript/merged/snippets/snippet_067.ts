test('test_face_variants', () => {
        const objContent = `# Different face formats
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 1.0 1.0 0.0
v 0.0 1.0 0.0

f 1 2 3 4

v 2.0 0.0 0.0
v 3.0 0.0 0.0
v 3.0 1.0 0.0
f 5/1 6/2 7/2/1

v 4.0 0.0 0.0
v 5.0 0.0 0.0
v 5.0 1.0 0.0
f 9/10/1 11/2/1

v 6.0 0.0 0.0
v 7.0 0.0 0.0
v 7.0 1.0 0.0
vn 0.0 0.0 1.0
f 13/14/1 15/1
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        options.fileName = "test.obj";
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        expect(scene.rootNode.childNodes.length).toBeGreaterThan(0);
    })