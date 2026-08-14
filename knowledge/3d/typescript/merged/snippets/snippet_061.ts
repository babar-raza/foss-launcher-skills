describe('TestGltfMaterialImport', () => {
    it('testMaterialImportFromBoombox', () => {
        const scene = new Scene();
        const options = new GltfLoadOptions();
        const file_path = '../foss.3d.python/examples/gltf2/BoomBox/glTF/BoomBox.gltf';

        if (fs.existsSync(file_path)) {
            const buffer = fs.readFileSync(file_path);
            scene.openFromBuffer(buffer, options);

            expect(scene.rootNode.childNodes.length).toBe(1);

            const node = scene.rootNode.childNodes[0];
            expect(node.material).toBeDefined();
            expect(node.material instanceof PbrMaterial).toBe(true);

            const material = node.material as PbrMaterial;
            expect(material.name).toBe('BoomBox_Mat');
            if (material.albedo) {
                expect(material.albedo.x).toBe(1.0);
                expect(material.albedo.y).toBe(1.0);
                expect(material.albedo.z).toBe(1.0);
            }
            expect(material.metallicFactor).toBe(0.0);
            expect(material.roughnessFactor).toBe(1.0);
            expect(material.transparency).toBe(0.0);
        } else {
            pending(`File not found: ${file_path}`);
        }
    });

    it('testPbrMaterialCreation', () => {
        const material = new PbrMaterial('TestMaterial');
        
        expect(material.name).toBe('TestMaterial');
        expect(material.metallicFactor).toBe(0.0);
        expect(material.roughnessFactor).toBe(0.0);
        expect(material.transparency).toBe(0.0);
    });

    it('testMaterialPropertySetters', () => {
        const material = new PbrMaterial();

        material.metallicFactor = 0.8;
        expect(material.metallicFactor).toBe(0.8);

        material.roughnessFactor = 0.3;
        expect(material.roughnessFactor).toBe(0.3);

        material.transparency = 0.5;
        expect(material.transparency).toBe(0.5);

        material.emissiveColor = new Vector3(0.1, 0.2, 0.3);
        if (material.emissiveColor) {
            expect(material.emissiveColor.x).toBeCloseTo(0.1, 3);
            expect(material.emissiveColor.y).toBeCloseTo(0.2, 3);
            expect(material.emissiveColor.z).toBeCloseTo(0.3, 3);
        }
    });
})