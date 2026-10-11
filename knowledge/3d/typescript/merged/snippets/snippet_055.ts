it('testMaterialPropertySetters', () => {
        const material = new PbrMaterial();

        material.metallicFactor = 0.8;
        expect(material.metallicFactor).toBe(0.8);

        material.roughnessFactor = 0.3;
        expect(material.roughnessFactor).toBe(0.3);

        material.transparency = 0.5;
        expect(material.transparency).toBe(0.5);

        material.emissiveColor = new Vector3(0.1, 0.2, 0.3);
        if (material.emissiveColor) {
            expect(material.emissiveColor.x).toBeCloseTo(0.1, 3);
            expect(material.emissiveColor.y).toBeCloseTo(0.2, 3);
            expect(material.emissiveColor.z).toBeCloseTo(0.3, 3);
        }
    })