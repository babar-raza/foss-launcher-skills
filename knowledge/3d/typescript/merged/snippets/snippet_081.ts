test('test_plugin_singleton', () => {
        const ioService = IOService.instance;
        const objPlugin1 = ioService.getPluginForExtension('.obj');
        const objPlugin2 = ioService.getPluginForExtension('.obj');
        
        expect(objPlugin1).toBe(objPlugin2);
        
        const stlPlugin1 = ioService.getPluginForExtension('.stl');
        const stlPlugin2 = ioService.getPluginForExtension('.stl');
        
        expect(stlPlugin1).toBe(stlPlugin2);
    })