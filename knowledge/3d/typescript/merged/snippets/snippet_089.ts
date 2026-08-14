describe('TestPluginSystem', () => {
    test('test_plugin_registration', () => {
        const ioService = IOService.instance;
        
        const objPlugin = ioService.getPluginForExtension('.obj');
        const stlPlugin = ioService.getPluginForExtension('.stl');
        const gltfPlugin = ioService.getPluginForExtension('.gltf');
        const threeMfPlugin = ioService.getPluginForExtension('.3mf');
        const fbxPlugin = ioService.getPluginForExtension('.fbx');
        
        expect(objPlugin).not.toBeNull();
        expect(stlPlugin).not.toBeNull();
        expect(gltfPlugin).not.toBeNull();
        expect(threeMfPlugin).not.toBeNull();
        expect(fbxPlugin).not.toBeNull();
    });

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
    });

    test('test_get_plugin_by_extension', () => {
        const ioService = IOService.instance;
        const objPlugin = ioService.getPluginForExtension('.obj')!;
        const stlPlugin = ioService.getPluginForExtension('.stl')!;
        
        const objPluginClass = objPlugin.constructor;
        const stlPluginClass = stlPlugin.constructor;
        
        expect(objPlugin).toBeInstanceOf(objPluginClass);
        expect(stlPlugin).toBeInstanceOf(stlPluginClass);
    });

    test('test_get_plugin_by_extension_case_insensitive', () => {
        const ioService = IOService.instance;
        const objPlugin1 = ioService.getPluginForExtension('.obj');
        const objPlugin2 = ioService.getPluginForExtension('.OBJ');
        const objPlugin3 = ioService.getPluginForExtension('.Obj');
        
        expect(objPlugin1).toBe(objPlugin2);
        expect(objPlugin1).toBe(objPlugin3);
    });

    test('test_plugin_creates_load_options', () => {
        const ioService = IOService.instance;
        const objPlugin = ioService.getPluginForExtension('.obj')!;
        const stlPlugin = ioService.getPluginForExtension('.stl')!;
        
        const objLoadOpts = objPlugin.createLoadOptions();
        const stlLoadOpts = stlPlugin.createLoadOptions();
        
        expect(objLoadOpts).not.toBeNull();
        expect(stlLoadOpts).not.toBeNull();
    });

    test('test_plugin_creates_save_options', () => {
        const ioService = IOService.instance;
        const objPlugin = ioService.getPluginForExtension('.obj')!;
        const stlPlugin = ioService.getPluginForExtension('.stl')!;
        
        const objSaveOpts = objPlugin.createSaveOptions();
        const stlSaveOpts = stlPlugin.createSaveOptions();
        
        expect(objSaveOpts).not.toBeNull();
        expect(stlSaveOpts).not.toBeNull();
    });

    test('test_plugin_registers_components', () => {
        const ioService = IOService.instance;
        
        const objPlugin = ioService.getPluginForExtension('.obj')!;
        const stlPlugin = ioService.getPluginForExtension('.stl')!;
        
        const objImporter = objPlugin.getImporter();
        const objExporter = objPlugin.getExporter();
        const objDetector = objPlugin.getFormatDetector();
        
        const stlImporter = stlPlugin.getImporter();
        const stlExporter = stlPlugin.getExporter();
        const stlDetector = stlPlugin.getFormatDetector();
        
        expect(objImporter).not.toBeNull();
        expect(objExporter).not.toBeNull();
        expect(objDetector).not.toBeNull();
        
        expect(stlImporter).not.toBeNull();
        expect(stlExporter).not.toBeNull();
        expect(stlDetector).not.toBeNull();
    });

    test('test_plugin_singleton', () => {
        const ioService = IOService.instance;
        const objPlugin1 = ioService.getPluginForExtension('.obj');
        const objPlugin2 = ioService.getPluginForExtension('.obj');
        
        expect(objPlugin1).toBe(objPlugin2);
        
        const stlPlugin1 = ioService.getPluginForExtension('.stl');
        const stlPlugin2 = ioService.getPluginForExtension('.stl');
        
        expect(stlPlugin1).toBe(stlPlugin2);
    });
})