it('testMaterialImport', () => {
        const scene = new Scene();
        const options = plugin.createLoadOptions();
        const filePath = '../foss.3d.python/examples/3mf/dodeca_chain_loop_color.3mf';

        scene.open(filePath, options);

        expect(scene.rootNode.childNodes.length).toBeGreaterThanOrEqual(1);
    })