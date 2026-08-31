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
    })