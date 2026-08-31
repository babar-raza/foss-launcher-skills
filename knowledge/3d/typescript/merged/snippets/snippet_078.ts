test('test_plugin_creates_load_options', () => {
        const ioService = IOService.instance;
        const objPlugin = ioService.getPluginForExtension('.obj')!;
        const stlPlugin = ioService.getPluginForExtension('.stl')!;
        
        const objLoadOpts = objPlugin.createLoadOptions();
        const stlLoadOpts = stlPlugin.createLoadOptions();
        
        expect(objLoadOpts).not.toBeNull();
        expect(stlLoadOpts).not.toBeNull();
    })