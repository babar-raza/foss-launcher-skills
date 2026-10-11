test('test_plugin_creates_save_options', () => {
        const ioService = IOService.instance;
        const objPlugin = ioService.getPluginForExtension('.obj')!;
        const stlPlugin = ioService.getPluginForExtension('.stl')!;
        
        const objSaveOpts = objPlugin.createSaveOptions();
        const stlSaveOpts = stlPlugin.createSaveOptions();
        
        expect(objSaveOpts).not.toBeNull();
        expect(stlSaveOpts).not.toBeNull();
    })