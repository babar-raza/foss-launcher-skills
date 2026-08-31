it('testLambertMaterialImport', () => {
        const options = new ColladaLoadOptions();
        options.enableMaterials = true;

        const file_path = '../foss.3d.python/examples/collada/sphere.dae';

        if (require('fs').existsSync(file_path)) {
            const scene = new Scene();
            scene.open(file_path, options);

            expect(scene.rootNode).toBeDefined();

            let sphereNode: Node | null = null;
            for (const node of scene.rootNode.childNodes) {
                if (node.name.toLowerCase().includes('sphere')) {
                    sphereNode = node;
                    break;
                }
            }

            expect(sphereNode).toBeDefined();
            expect(sphereNode).not.toBeNull();
            const sphereNodeChecked = sphereNode!;
            expect(sphereNodeChecked.material).toBeDefined();
            expect(sphereNodeChecked.material!.constructor.name).toBe('LambertMaterial');

            const material = sphereNodeChecked.material! as LambertMaterial;
            expect(material.diffuseColor).toBeDefined();
            expect(material.diffuseColor!.x).toBeCloseTo(0.5, 3);
            expect(material.diffuseColor!.y).toBeCloseTo(0.5, 3);
            expect(material.diffuseColor!.z).toBeCloseTo(0.5, 3);
        } else {
            pending(`File not found: ${file_path}`);
        }
    })