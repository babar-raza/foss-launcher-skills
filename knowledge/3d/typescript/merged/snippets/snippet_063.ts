it('testPbrMaterialCreation', () => {
        const material = new PbrMaterial('TestMaterial');
        
        expect(material.name).toBe('TestMaterial');
        expect(material.metallicFactor).toBe(0.0);
        expect(material.roughnessFactor).toBe(0.0);
        expect(material.transparency).toBe(0.0);
    })