test('test_get_plugin_by_extension_case_insensitive', () => {
        const ioService = IOService.instance;
        const objPlugin1 = ioService.getPluginForExtension('.obj');
        const objPlugin2 = ioService.getPluginForExtension('.OBJ');
        const objPlugin3 = ioService.getPluginForExtension('.Obj');
        
        expect(objPlugin1).toBe(objPlugin2);
        expect(objPlugin1).toBe(objPlugin3);
    })