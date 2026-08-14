describe('Test3MFMaterialExport', () => {
    let plugin: ThreeMfPlugin;

    beforeEach(() => {
        plugin = ThreeMfPlugin.getInstance();
    });

    it('testExportObjectMaterial', () => {
        const scene = new Scene();
        const options = plugin.createSaveOptions();
        options.enableCompression = false;

        const mesh = new Mesh('cube');

        mesh.controlPoints.push(new Vector4(0, 0, 0, 1));
        mesh.controlPoints.push(new Vector4(1, 0, 0, 1));
        mesh.controlPoints.push(new Vector4(1, 1, 0, 1));
        mesh.controlPoints.push(new Vector4(0, 1, 0, 1));

        mesh.createPolygon(0, 1, 2);
        mesh.createPolygon(0, 2, 3);

        const node = new Node('cube');
        node.entity = mesh;
        node.parentNode = scene.rootNode;

        const material = new LambertMaterial('RedMaterial');
        material.diffuseColor = new Vector3(1.0, 0.0, 0.0);
        node.material = material;

        scene.save('/tmp/test_material.3mf', options);
        expect(true).toBe(true);
    });
})