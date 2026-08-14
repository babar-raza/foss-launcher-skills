describe('TestObjImporter', () => {
    test('test_basic_cube_import', () => {
        const objContent = `# Simple cube OBJ
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 1.0 1.0 0.0
v 0.0 1.0 0.0
f 1 2 3 4
f 5 6 7 8
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        options.fileName = "test.obj";
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        expect(scene.rootNode).not.toBeNull();
        expect(scene.rootNode.childNodes.length).toBeGreaterThan(0);
        
        const node = scene.rootNode.childNodes[0];
        expect(node.entity).not.toBeNull();
    });

    test('test_multiple_objects', () => {
        const objContent = `# Multiple objects
o Cube1
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 1.0 1.0 0.0
v 0.0 1.0 0.0
f 1 2 3 4

o Cube2
v 2.0 0.0 0.0
v 3.0 0.0 0.0
v 3.0 1.0 0.0
v 2.0 1.0 0.0
f 5 6 7 8
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        options.fileName = "test.obj";
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        expect(scene.rootNode.childNodes.length).toBeGreaterThanOrEqual(2);
    });

    test('test_groups', () => {
        const objContent = `# Groups
o MyObject
g Group1
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 1.0 1.0 0.0
v 0.0 1.0 0.0
f 1 2 3 4

g Group2
v 2.0 0.0 0.0
v 3.0 0.0 0.0
v 3.0 1.0 0.0
v 2.0 1.0 0.0
f 5 6 7 8
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        options.fileName = "test.obj";
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        expect(scene.rootNode.childNodes.length).toBeGreaterThan(0);
    });

    test('test_normals_and_uvs', () => {
        const objContent = `# With normals and UVs
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 1.0 1.0 0.0
v 0.0 1.0 0.0
vt 0.0 0.0
vt 1.0 0.0
vt 1.0 1.0
vt 0.0 1.0
vt 0.0 1.0
vn 0.0 0.0 1.0
f 1/1/1 2/2/1 3/3/1 4/4/1
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        options.fileName = "test.obj";
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        expect(scene.rootNode.childNodes.length).toBeGreaterThan(0);
        
        const node = scene.rootNode.childNodes[0];
        expect(node.entity).not.toBeNull();
    });

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
    });

    test('test_flip_coordinate_system', () => {
        const objContent = `# Test coordinate flip
v 1.0 2.0 3.0
v 2.0 3.0 4.0
v 3.0 4.0 5.0
f 1 2 3
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        options.flipCoordinateSystem = true;
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        expect(scene.rootNode.childNodes.length).toBeGreaterThan(0);
        
        const node = scene.rootNode.childNodes[0];
        expect(node.entity).not.toBeNull();
    });

    test('test_scale', () => {
        const objContent = `# Test scaling
o TestMesh
v 1.0 1.0 1.0
v 2.0 2.0 2.0
v 3.0 2.0 2.0
f 1 2 3
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        options.scale = 2.0;
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        expect(scene.rootNode.childNodes.length).toBeGreaterThan(0);
        
        const node = scene.rootNode.childNodes[0];
        expect(node.entity).not.toBeNull();
    });

    test('test_smoothing_groups', () => {
        const objContent = `# Test smoothing groups
o TestMe