it('testSceneOpenBinaryStlFile', () => {
        const file_path = '../foss.3d.python/examples/stl/stl_binary.stl';

        if (require('fs').existsSync(file_path)) {
            const scene = Scene.fromFile(file_path);

            expect(scene.rootNode).toBeDefined();
            expect(scene.rootNode.childNodes.length).toBe(1);

            const node = scene.rootNode.childNodes[0];
            expect(node.entity).toBeDefined();

            const mesh = node.entity as Mesh;
            expect(mesh!.controlPoints.length).toBe(6000);
            expect(mesh!.polygonCount).toBe(2000);
        } else {
            pending(`File not found: ${file_path}`);
        }
    })