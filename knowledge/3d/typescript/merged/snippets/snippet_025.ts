it('testMaterialsDisabled', () => {
        const options = new ColladaLoadOptions();
        options.enableMaterials = false;

        const file_path = '../foss.3d.python/examples/collada/cube_triangulate.dae';

        if (require('fs').existsSync(file_path)) {
            const scene = new Scene();
            scene.open(file_path, options);

            expect(scene.rootNode).toBeDefined();

            let boxNode: Node | null = null;
            for (const node of scene.rootNode.childNodes) {
                if (node.name === 'Box') {
                    boxNode = node;
                    break;
                }
            }

            expect(boxNode).toBeDefined();
            expect(boxNode).not.toBeNull();
            expect(boxNode!.material).toBeNull();
        } else {
            pending(`File not found: ${file_path}`);
        }
    })