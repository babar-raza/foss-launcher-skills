test('test_get_plugin_by_extension', () => {
        const ioService = IOService.instance;
        const objPlugin = ioService.getPluginForExtension('.obj')!;
        const stlPlugin = ioService.getPluginForExtension('.stl')!;
        
        const objPluginClass = objPlugin.constructor;
        const stlPluginClass = stlPlugin.constructor;
        
        expect(objPlugin).toBeInstanceOf(objPluginClass);
        expect(stlPlugin).toBeInstanceOf(stlPluginClass);
    })