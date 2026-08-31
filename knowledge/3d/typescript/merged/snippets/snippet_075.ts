test('test_get_plugin_by_format', () => {
        const ioService = IOService.instance;
        const objFormat = new ObjFormat();
        const stlFormat = new StlFormat();
        const threeMfFormat = ioService.getPluginForExtension('.3mf')!.getFileFormat();

        const objPlugin = ioService.getPluginForFormat(objFormat)!;
        const stlPlugin = ioService.getPluginForFormat(stlFormat)!;
        const threeMfPlugin = ioService.getPluginForFormat(threeMfFormat)!;
        
        const objPluginClass = objPlugin.constructor;
        const stlPluginClass = stlPlugin.constructor;
        const threeMfPluginClass = threeMfPlugin.constructor;
        
        expect(objPlugin).toBeInstanceOf(objPluginClass);
        expect(stlPlugin).toBeInstanceOf(stlPluginClass);
        expect(threeMfPlugin).toBeInstanceOf(threeMfPluginClass);
    })