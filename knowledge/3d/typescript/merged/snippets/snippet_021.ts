describe('TestColladaMaterials', () => {
    it('testPhongMaterialImport', () => {
        const options = new ColladaLoadOptions();
        options.enableMaterials = true;

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
            const boxNodeChecked = boxNode!;
            expect(boxNodeChecked.material).toBeDefined();
            expect(boxNodeChecked.material!.constructor.name).toBe('PhongMaterial');

            const material = boxNodeChecked.material! as PhongMaterial;
            expect(material.diffuseColor).toBeDefined();
            expect(material.diffuseColor!.x).toBeCloseTo(0.137255, 5);
            expect(material.diffuseColor!.y).toBeCloseTo(0.403922, 5);
            expect(material.diffuseColor!.z).toBeCloseTo(0.870588, 5);

            expect(material.specularColor).toBeDefined();
            expect(material.emissiveColor).toBeDefined();
            expect(material.ambientColor).toBeDefined();

            expect(material.shininess).toBeCloseTo(16.0, 1);
            expect(material.transparency).toBeCloseTo(0.0, 1);
        } else {
            pending(`File not found: ${file_path}`);
        }
    });

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
    });

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
    });
})