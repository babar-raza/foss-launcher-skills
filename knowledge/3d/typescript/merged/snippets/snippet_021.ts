it('testImportRealCube', () => {
        const scene = new Scene();
        const options = new ColladaLoadOptions();

        const file_path = '../foss.3d.python/examples/collada/cube_triangulate.dae';

        if (require('fs').existsSync(file_path)) {
            scene.open(file_path, options);

            expect(scene.rootNode).toBeDefined();
            expect(scene.rootNode.childNodes.length).toBeGreaterThan(0);
        } else {
            pending(`File not found: ${file_path}`);
        }
    })