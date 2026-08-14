def test_pbr_material_creation(self):
        from aspose.threed.shading import PbrMaterial
        from aspose.threed.utilities import Vector3

        albedo = Vector3(0.5, 0.6, 0.7)
        material = PbrMaterial('TestMaterial', albedo)

        self.assertEqual(material.name, 'TestMaterial')
        self.assertEqual(material.albedo, albedo)
        self.assertEqual(material.metallic_factor, 0.0)
        self.assertEqual(material.roughness_factor, 0.0)
        self.assertEqual(material.transparency, 0.0)